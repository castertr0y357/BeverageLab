import os
import requests
import json
import re
import time
import logging
from typing import List, Dict, Any, Optional, Union, Generator

from ..models import LLMProvider, SystemConfiguration
from .prompts import AIPromptsMixin

logger = logging.getLogger(__name__)



class AIProvidersMixin:
    @classmethod
    def _resolve_base_url(cls, provider: LLMProvider, default_url: str = "") -> str:
            """Resolve base URL, translating localhost/127.0.0.1 to host.docker.internal if running in Docker."""
            base_url = provider.base_url or default_url
            if os.path.exists('/.dockerenv'):
                if "localhost" in base_url:
                    base_url = base_url.replace("localhost", "host.docker.internal")
                elif "127.0.0.1" in base_url:
                    base_url = base_url.replace("127.0.0.1", "host.docker.internal")
            return base_url

    @classmethod
    def get_default_provider(cls) -> Optional[LLMProvider]:
            """Get the default LLM provider configured in the system."""
            config = SystemConfiguration.get_config()
            if config.default_llm_provider and config.default_llm_provider.is_enabled:
                return config.default_llm_provider
            
            # Fallback to the first enabled provider if default is missing
            return LLMProvider.objects.filter(is_enabled=True).first()

    @staticmethod
    def _safe_request(method: str, url: str, attempts: int = 3, timeout: int = 30, **kwargs: Any) -> requests.Response:
            """Execute a request with automated retry logic and exponential backoff."""
            from urllib.parse import urlparse
            import socket
            try:
                parsed = urlparse(url)
                hostname = parsed.hostname
                if hostname:
                    ip = socket.gethostbyname(hostname)
                    if ip == "169.254.169.254" or ip.startswith("169.254."):
                        raise ValueError("SSRF Block: Link-local and metadata IPs are banned.")
            except Exception as e:
                if "SSRF Block" in str(e):
                    raise e
    
            last_error = None
            for i in range(attempts):
                try:
                    # Escalating timeout for each retry
                    current_timeout = timeout + (i * 15)
                    response = requests.request(method, url, timeout=current_timeout, **kwargs)
                    response.raise_for_status()
                    return response
                except (requests.exceptions.RequestException, requests.exceptions.Timeout) as e:
                    last_error = e
                    # Don't sleep on last attempt
                    if i < attempts - 1:
                        import time
                        time.sleep(1.5 * (i + 1)) # Exponential backoff: 1.5s, 3s...
                    continue
            
            # If we get here, all attempts failed
            raise last_error

    @staticmethod
    def _extract_json(text: str) -> Optional[Any]:
            """Resiliently extract the first JSON object or array from a string."""
            if not text:
                return None
            try:
                # Look for everything between the first { or [ and the last } or ]
                match = re.search(r'([\[\{].*[\]\}])', text, re.DOTALL)
                if match:
                    return json.loads(match.group(1))
                # Fallback: direct attempt
                return json.loads(text)
            except (json.JSONDecodeError, ValueError):
                return None

    @classmethod
    def check_status(cls) -> str:
            """
            Actively check if the configured AI provider is reachable and responsive.
            Returns: 'synchronized', 'dormant', or 'no_provider'
            """
            provider = cls.get_default_provider()
            if not provider:
                return 'no_provider'
    
            try:
                if provider.provider_type == 'OLLAMA':
                    base = cls._resolve_base_url(provider, "http://localhost:11434").rstrip('/')
                    model = provider.default_model or "mistral"
                    r = requests.post(f"{base}/api/show", json={"name": model}, timeout=10)
                    if r.status_code == 200:
                        # Also keep warm while we're at it
                        cls.keep_warm()
                        return 'synchronized'
                    return 'dormant'
                elif provider.provider_type in ['OPENAI', 'CLAUDE', 'GEMINI', 'CUSTOM', 'ANYTHINGLLM']:
                    # For cloud providers, attempt a lightweight model list call to verify the API key works
                    models = cls.list_models(provider)
                    return 'synchronized' if models else 'dormant'
                else:
                    return 'dormant'
            except Exception as e:
                logger.error(f"AIStatusCheck - Error - Laboratory Status Pulse Failure: {e}")
                return 'dormant'

    @classmethod
    def list_models(cls, provider: LLMProvider) -> List[str]:
            """Fetch available models from the provider's API."""
            try:
                if provider.provider_type in ['OPENAI', 'CLAUDE', 'CUSTOM', 'ANYTHINGLLM']:
                    return cls._list_openai_models(provider)
                elif provider.provider_type == 'OLLAMA':
                    return cls._list_ollama_models(provider)
                elif provider.provider_type == 'GEMINI':
                    return cls._list_gemini_models(provider)
                else:
                    return []
            except Exception as e:
                logger.error(f"AIModelsFetch - Error - Error fetching models: {e}")
                return []

    @classmethod
    def _list_openai_models(cls, provider: LLMProvider) -> List[str]:
            url = cls._resolve_base_url(provider, "https://api.openai.com/v1").rstrip('/') + "/models"
            headers = {"Authorization": f"Bearer {provider.api_key}"} if provider.api_key else {}
            if provider.provider_type == 'CLAUDE':
                headers = {
                    "x-api-key": provider.api_key,
                    "anthropic-version": "2023-06-01"
                }
            
            response = cls._safe_request('GET', url, headers=headers, timeout=10)
            data = response.json()
            return [m['id'] for m in data.get('data', [])]

    @classmethod
    def _list_ollama_models(cls, provider: LLMProvider) -> List[str]:
            url = cls._resolve_base_url(provider, "http://localhost:11434").rstrip('/') + "/api/tags"
            response = cls._safe_request('GET', url, timeout=10)
            data = response.json()
            return [m['name'] for m in data.get('models', [])]

    @classmethod
    def _list_gemini_models(cls, provider: LLMProvider) -> List[str]:
            api_key = provider.api_key
            url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
            response = cls._safe_request('GET', url, timeout=10)
            data = response.json()
            # Filter for models that support generateContent
            return [m['name'].replace('models/', '') for m in data.get('models', []) 
                    if 'generateContent' in m.get('supportedGenerationMethods', [])]

    @classmethod
    def _call_openai(cls, provider: LLMProvider, messages: List[Dict[str, str]], mode: str = "standard") -> str:
            url = cls._resolve_base_url(provider, "https://api.openai.com/v1/chat/completions")
            headers = {
                "Authorization": f"Bearer {provider.api_key}",
                "Content-Type": "application/json"
            }
            model_name = provider.default_model or "gpt-3.5-turbo"
            data = {
                "model": model_name,
                "messages": messages,
                "temperature": 0.9 if mode == 'experimental' else 0.3,
                "top_p": 0.95 if mode == 'experimental' else 0.5
            }
            if model_name.startswith('o1') or model_name.startswith('o3'):
                if getattr(provider, 'enable_thinking', False):
                    data["reasoning_effort"] = getattr(provider, 'thinking_effort', 'medium')
                else:
                    data["reasoning_effort"] = "low"
            else:
                # Enforce JSON output mode if a structured data query is detected
                user_prompt = messages[-1]['content'] if messages else ""
                is_json_request = any(keyword in user_prompt for keyword in ["[STRUCTURED DATA REQUEST]", "[BATCH CHEMICAL ANALYSIS]", "RAW JSON", "Return ONLY a JSON object"])
                is_surprise_request = any(keyword in user_prompt for keyword in ["[AUTONOMOUS SYNTHESIS REQUEST]"])
                enable_thinking = getattr(provider, 'enable_thinking', False) and ("o1" in model_name.lower() or "o3" in model_name.lower())
                if is_surprise_request:
                    data["response_format"] = {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "surprise_mix",
                            "strict": True,
                            "schema": AIPromptsMixin.get_surprise_mix_json_schema(enable_thinking)
                        }
                    }
                elif is_json_request:
                    data["response_format"] = {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "beverage_recommendation",
                            "strict": True,
                            "schema": AIPromptsMixin.get_autonomous_json_schema(enable_thinking)
                        }
                    }
    
            response = cls._safe_request('POST', url, headers=headers, json=data, timeout=30)
            result = response.json()
            
            content = result['choices'][0]['message']['content'] if 'choices' in result else ""
            
            logger.info(f"AISynthesis - Info - Raw LLM Signal ({provider.name}): {len(content)} characters received.")
            if not content.strip():
                 logger.warning(f"AISynthesis - Warning - Empty signal from {provider.name}! Full response: {result}")
                 
            return content

    @classmethod
    def _call_ollama(cls, provider: LLMProvider, messages: List[Dict[str, str]], mode: str = "standard") -> str:
            # Ollama /api/chat — native format.
            url = cls._resolve_base_url(provider, "http://localhost:11434").rstrip('/') + "/api/chat"
            model_name = provider.default_model or "mistral"
            if getattr(provider, 'enable_thinking', False):
                if "gpt-oss" in model_name.lower():
                    think_val = getattr(provider, 'thinking_effort', 'medium')
                else:
                    think_val = True
            else:
                think_val = False
    
            data = {
                "model": model_name,
                "messages": messages,
                "stream": False,
                "think": think_val,
                "options": {
                    "num_predict": 2048,
                    "temperature": 0.9 if mode == 'experimental' else 0.3,
                    "top_p": 0.95 if mode == 'experimental' else 0.5
                }
            }
            user_prompt = messages[-1]['content'] if messages else ""
            is_json_request = any(keyword in user_prompt for keyword in ["[STRUCTURED DATA REQUEST]", "[BATCH CHEMICAL ANALYSIS]", "RAW JSON", "Return ONLY a JSON object"])
            is_surprise_request = any(keyword in user_prompt for keyword in ["[AUTONOMOUS SYNTHESIS REQUEST]"])
            enable_thinking = getattr(provider, 'enable_thinking', False) and ("think" in model_name.lower() or "deepseek" in model_name.lower() or "r1" in model_name.lower())
            if is_surprise_request:
                data["format"] = AIPromptsMixin.get_surprise_mix_json_schema(enable_thinking)
            elif is_json_request:
                data["format"] = AIPromptsMixin.get_autonomous_json_schema(enable_thinking)
    
            logger.warning(f"Ollama Chat - Request payload: {json.dumps(data)}")
            response = cls._safe_request('POST', url, json=data, timeout=120)
            result = response.json()
            
            content = result.get('message', {}).get('content', "")
            
            logger.info(f"AISynthesis - Info - Raw LLM Signal (Ollama): {len(content)} characters received.")
            if not content.strip():
                 logger.warning(f"AISynthesis - Warning - Empty signal from Ollama! Full Response: {result}")
                 
            return content

    @classmethod
    def _call_claude(cls, provider: LLMProvider, messages: List[Dict[str, str]], mode: str = "standard") -> str:
            url = "https://api.anthropic.com/v1/messages"
            headers = {
                "x-api-key": provider.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            }
            system = messages[0]['content']
            actual_messages = messages[1:]
            
            model_name = provider.default_model or "claude-3-haiku-20240307"
            
            data = {
                "model": model_name,
                "system": system,
                "messages": actual_messages,
                "max_tokens": 1024,
                "temperature": 0.9 if mode == 'experimental' else 0.3,
                "top_p": 0.95 if mode == 'experimental' else 0.5,
}
            
            if "claude-3-7" in model_name.lower() or "sonnet" in model_name.lower():
                if getattr(provider, 'enable_thinking', False):
                    budget = 1024 if getattr(provider, 'thinking_effort', 'medium') == 'low' else (2048 if getattr(provider, 'thinking_effort', 'medium') == 'medium' else 4096)
                    data["thinking"] = {
                        "type": "enabled",
                        "budget_tokens": budget
                    }
                    data["max_tokens"] = budget + 1024
    
            response = cls._safe_request('POST', url, headers=headers, json=data, timeout=30)
            return response.json()['content'][0]['text']

    @classmethod
    def _call_gemini(cls, provider: LLMProvider, messages: List[Dict[str, str]], mode: str = "standard") -> str:
            api_key = provider.api_key
            model = provider.default_model or "gemini-1.5-flash"
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            
            system_text = messages[0]['content'] if messages and messages[0]['role'] == 'system' else ""
            actual_messages = messages[1:] if system_text else messages
            
            contents = []
            for m in actual_messages:
                role = "user" if m['role'] == 'user' else "model"
                contents.append({"role": role, "parts": [{"text": m['content']}]})
                
            data: Dict[str, Any] = {"contents": contents}
            if system_text:
                data["system_instruction"] = {"parts": [{"text": system_text}]}
                
            user_prompt = messages[-1]['content'] if messages else ""
            is_json_request = any(keyword in user_prompt for keyword in ["[STRUCTURED DATA REQUEST]", "[BATCH CHEMICAL ANALYSIS]", "RAW JSON", "Return ONLY a JSON object"])
            is_surprise_request = any(keyword in user_prompt for keyword in ["[AUTONOMOUS SYNTHESIS REQUEST]"])
            enable_thinking = getattr(provider, 'enable_thinking', False) and "thinking" in model.lower()
            
            generation_config = {}
            generation_config["temperature"] = 0.9 if mode == 'experimental' else 0.3
            generation_config["topP"] = 0.95 if mode == 'experimental' else 0.5
            if is_surprise_request:
                generation_config["responseMimeType"] = "application/json"
                generation_config["responseSchema"] = AIPromptsMixin.get_surprise_mix_json_schema(enable_thinking)
            elif is_json_request:
                generation_config["responseMimeType"] = "application/json"
                generation_config["responseSchema"] = AIPromptsMixin.get_autonomous_json_schema(enable_thinking)
                
            if "thinking" in model.lower():
                if getattr(provider, 'enable_thinking', False):
                    budget = 1024 if getattr(provider, 'thinking_effort', 'medium') == 'low' else (2048 if getattr(provider, 'thinking_effort', 'medium') == 'medium' else 4096)
                    generation_config["thinkingConfig"] = {"thinkingBudget": budget}
                else:
                    generation_config["thinkingConfig"] = {"thinkingBudget": 0}
                    
            if generation_config:
                data["generationConfig"] = generation_config
    
            response = cls._safe_request('POST', url, json=data, timeout=30)
            result = response.json()
            
            try:
                content = result['candidates'][0]['content']['parts'][0]['text']
            except (KeyError, IndexError):
                content = ""
                
            logger.info(f"AISynthesis - Info - Raw LLM Signal (Gemini): {len(content)} characters received.")
            if not content.strip():
                 logger.warning(f"AISynthesis - Warning - Empty signal from Gemini! Full Response: {result}")
                 
            return content

    @classmethod
    def _call_openai_stream(cls, provider: LLMProvider, messages: List[Dict[str, str]], mode: str = "standard") -> Generator[str, None, None]:
            url = cls._resolve_base_url(provider, "https://api.openai.com/v1/chat/completions")
            headers = {
                "Authorization": f"Bearer {provider.api_key}",
                "Content-Type": "application/json"
            }
            model_name = provider.default_model or "gpt-3.5-turbo"
            data = {"model": model_name, "messages": messages, "temperature": 0.9 if mode == 'experimental' else 0.3,
                "top_p": 0.95 if mode == 'experimental' else 0.5, "stream": True}
            if model_name.startswith('o1') or model_name.startswith('o3'):
                if getattr(provider, 'enable_thinking', False):
                    data["reasoning_effort"] = getattr(provider, 'thinking_effort', 'medium')
                else:
                    data["reasoning_effort"] = "low"
            else:
                user_prompt = messages[-1]['content'] if messages else ""
                is_json_request = any(keyword in user_prompt for keyword in ["[STRUCTURED DATA REQUEST]", "[BATCH CHEMICAL ANALYSIS]", "RAW JSON", "Return ONLY a JSON object"])
                is_surprise_request = any(keyword in user_prompt for keyword in ["[AUTONOMOUS SYNTHESIS REQUEST]"])
                enable_thinking = getattr(provider, 'enable_thinking', False) and ("o1" in model_name.lower() or "o3" in model_name.lower())
                if is_surprise_request:
                    data["response_format"] = {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "surprise_mix",
                            "strict": True,
                            "schema": AIPromptsMixin.get_surprise_mix_json_schema(enable_thinking)
                        }
                    }
                elif is_json_request:
                    data["response_format"] = {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "beverage_recommendation",
                            "strict": True,
                            "schema": AIPromptsMixin.get_autonomous_json_schema(enable_thinking)
                        }
                    }
    
            response = requests.post(url, headers=headers, json=data, stream=True, timeout=60)
            response.raise_for_status()
            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith('data: '):
                        data_str = line_str[6:]
                        if data_str == '[DONE]': break
                        try:
                            data_json = json.loads(data_str)
                            if 'choices' in data_json and len(data_json['choices']) > 0:
                                delta = data_json['choices'][0].get('delta', {})
                                if 'content' in delta:
                                    yield f"data: {json.dumps({'chunk': delta['content']})}\n\n"
                        except json.JSONDecodeError: pass

    @classmethod
    def _call_ollama_stream(cls, provider: LLMProvider, messages: List[Dict[str, str]], mode: str = "standard") -> Generator[str, None, None]:
            url = cls._resolve_base_url(provider, "http://localhost:11434").rstrip('/') + "/api/chat"
            model_name = provider.default_model or "mistral"
            if getattr(provider, 'enable_thinking', False):
                if "gpt-oss" in model_name.lower():
                    think_val = getattr(provider, 'thinking_effort', 'medium')
                else:
                    think_val = True
            else:
                think_val = False
    
            data = {
                "model": model_name,
                "messages": messages,
                "stream": True,
                "think": think_val,
                "options": {
                    "num_predict": 2048,
                    "temperature": 0.9 if mode == 'experimental' else 0.3,
                    "top_p": 0.95 if mode == 'experimental' else 0.5
                }
            }
            user_prompt = messages[-1]['content'] if messages else ""
            is_json_request = any(keyword in user_prompt for keyword in ["[STRUCTURED DATA REQUEST]", "[BATCH CHEMICAL ANALYSIS]", "RAW JSON", "Return ONLY a JSON object"])
            is_surprise_request = any(keyword in user_prompt for keyword in ["[AUTONOMOUS SYNTHESIS REQUEST]"])
            enable_thinking = getattr(provider, 'enable_thinking', False) and ("think" in model_name.lower() or "deepseek" in model_name.lower() or "r1" in model_name.lower())
            if is_surprise_request:
                data["format"] = AIPromptsMixin.get_surprise_mix_json_schema(enable_thinking)
            elif is_json_request:
                data["format"] = AIPromptsMixin.get_autonomous_json_schema(enable_thinking)
    
            logger.warning(f"Ollama Stream Chat - Request payload: {json.dumps(data)}")
            response = requests.post(url, json=data, stream=True, timeout=120)
            response.raise_for_status()
            for line in response.iter_lines():
                if line:
                    try:
                        data_json = json.loads(line.decode('utf-8'))
                        if 'message' in data_json and 'content' in data_json['message']:
                            yield f"data: {json.dumps({'chunk': data_json['message']['content']})}\n\n"
                    except json.JSONDecodeError: pass

    @classmethod
    def _call_claude_stream(cls, provider: LLMProvider, messages: List[Dict[str, str]], mode: str = "standard") -> Generator[str, None, None]:
            url = "https://api.anthropic.com/v1/messages"
            headers = {"x-api-key": provider.api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
            system = messages[0]['content']
            actual_messages = messages[1:]
            
            model_name = provider.default_model or "claude-3-haiku-20240307"
            
            data = {
                "model": model_name,
                "system": system,
                "messages": actual_messages,
                "max_tokens": 1024,
                
                "temperature": 0.9 if mode == 'experimental' else 0.3,
                "top_p": 0.95 if mode == 'experimental' else 0.5,
"stream": True
            }
            
            if "claude-3-7" in model_name.lower() or "sonnet" in model_name.lower():
                if getattr(provider, 'enable_thinking', False):
                    budget = 1024 if getattr(provider, 'thinking_effort', 'medium') == 'low' else (2048 if getattr(provider, 'thinking_effort', 'medium') == 'medium' else 4096)
                    data["thinking"] = {
                        "type": "enabled",
                        "budget_tokens": budget
                    }
                    data["max_tokens"] = budget + 1024
    
            response = requests.post(url, headers=headers, json=data, stream=True, timeout=60)
            response.raise_for_status()
            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith('data: '):
                        data_str = line_str[6:]
                        try:
                            data_json = json.loads(data_str)
                            if data_json.get('type') == 'content_block_delta':
                                delta = data_json.get('delta', {})
                                if delta.get('type') == 'text_delta':
                                    yield f"data: {json.dumps({'chunk': delta.get('text', '')})}\n\n"
                        except json.JSONDecodeError: pass

    @classmethod
    def _call_gemini_stream(cls, provider: LLMProvider, messages: List[Dict[str, str]], mode: str = "standard") -> Generator[str, None, None]:
            api_key = provider.api_key
            model = provider.default_model or "gemini-1.5-flash"
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?alt=sse&key={api_key}"
            system_text = messages[0]['content'] if messages and messages[0]['role'] == 'system' else ""
            actual_messages = messages[1:] if system_text else messages
            contents = [{"role": "user" if m['role'] == 'user' else "model", "parts": [{"text": m['content']}]} for m in actual_messages]
            data = {"contents": contents}
            if system_text: data["system_instruction"] = {"parts": [{"text": system_text}]}
            
            user_prompt = messages[-1]['content'] if messages else ""
            is_json_request = any(keyword in user_prompt for keyword in ["[STRUCTURED DATA REQUEST]", "[BATCH CHEMICAL ANALYSIS]", "RAW JSON", "Return ONLY a JSON object"])
            is_surprise_request = any(keyword in user_prompt for keyword in ["[AUTONOMOUS SYNTHESIS REQUEST]"])
            enable_thinking = getattr(provider, 'enable_thinking', False) and "thinking" in model.lower()
            
            generation_config = {}
            generation_config["temperature"] = 0.9 if mode == 'experimental' else 0.3
            generation_config["topP"] = 0.95 if mode == 'experimental' else 0.5
            if is_surprise_request:
                generation_config["responseMimeType"] = "application/json"
                generation_config["responseSchema"] = AIPromptsMixin.get_surprise_mix_json_schema(enable_thinking)
            elif is_json_request:
                generation_config["responseMimeType"] = "application/json"
                generation_config["responseSchema"] = AIPromptsMixin.get_autonomous_json_schema(enable_thinking)
                
            if "thinking" in model.lower():
                if getattr(provider, 'enable_thinking', False):
                    budget = 1024 if getattr(provider, 'thinking_effort', 'medium') == 'low' else (2048 if getattr(provider, 'thinking_effort', 'medium') == 'medium' else 4096)
                    generation_config["thinkingConfig"] = {"thinkingBudget": budget}
                else:
                    generation_config["thinkingConfig"] = {"thinkingBudget": 0}
                    
            if generation_config:
                data["generationConfig"] = generation_config
    
            response = requests.post(url, json=data, stream=True, timeout=60)
            response.raise_for_status()
            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith('data: '):
                        data_str = line_str[6:]
                        try:
                            data_json = json.loads(data_str)
                            if 'candidates' in data_json and len(data_json['candidates']) > 0:
                                parts = data_json['candidates'][0].get('content', {}).get('parts', [])
                                if parts:
                                    yield f"data: {json.dumps({'chunk': parts[0].get('text', '')})}\n\n"
                        except json.JSONDecodeError: pass

