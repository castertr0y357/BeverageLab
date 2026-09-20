import json
import time
import os
import shutil
import re
from django.core.management.base import BaseCommand
from django.test import Client
from soda_mixer.flavors.models import Ingredient
from django.contrib.auth.models import User

class Command(BaseCommand):
    help = 'Runs QA evaluation against live AI generation endpoints'

    def handle(self, *args, **options):
        qa_dir = os.path.join(os.getcwd(), 'QA_recipes')
        if os.path.exists(qa_dir):
            shutil.rmtree(qa_dir)
        os.makedirs(qa_dir)
        
        user, _ = User.objects.get_or_create(username='qa_test_user', defaults={'password': 'qa_password'})
        client = Client()
        client.force_login(user)
        self.stdout.write(self.style.SUCCESS("Starting AI Evaluation QA..."))

        self.test_vibe_creation(client)
        self.test_quick_recommendations(client)
        self.test_ai_suggest(client)
        
        self.stdout.write(self.style.SUCCESS("\nEvaluation Complete!"))

    def _save_recipe(self, prefix, name, data, lab_mode="SODA"):
        clean_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', name)
        # Avoid naming collisions
        filename = f"{prefix}_{clean_name}_{int(time.time()*1000)}.md"
        filepath = os.path.join('QA_recipes', filename)
        
        # Determine if it's a full recipe or just suggestions
        is_suggestion = 'suggestions' in data
        ingredients = data.get('suggestions', []) if is_suggestion else data.get('ingredients', [])
        
        # Calculate QA Audit
        audit = []
        status = "PASS"
        
        total_parts = sum(float(i.get('amount', 0) or 0) for i in ingredients)
        
        if lab_mode in ['SODA', 'SLUSHIE']:
            if abs(total_parts - 100.0) <= 0.1:
                audit.append("- **Part Distribution Bounds**: PASS - Total parts sum to exactly 100.")
            else:
                audit.append(f"- **Part Distribution Bounds**: FAIL - Total parts sum to {total_parts:.1f}, expected 100.")
                status = "FAIL"
                
        if lab_mode == 'COFFEE':
            # Base beans check (check if there is any bean ingredient)
            has_beans = False
            for i in ingredients:
                if 'Bean' in i.get('name', '') or 'Espresso' in i.get('name', '') or 'Yirgacheffe' in i.get('name', '') or 'Mandheling' in i.get('name', ''):
                    has_beans = True
                    amt = float(i.get('amount', 0) or 0)
                    if abs(amt - 18.0) <= 0.1:
                        audit.append(f"- **Coffee Constraints**: PASS - Bean '{i.get('name')}' is exactly 18.0 parts.")
                    else:
                        audit.append(f"- **Coffee Constraints**: FAIL - Bean '{i.get('name')}' is {amt:.1f} parts, expected 18.0.")
                        status = "FAIL"
            if is_suggestion and not has_beans:
                audit.append("- **Coffee Constraints**: N/A - Suggestion mode, beans might be assumed in base.")
                
        # Lookup DB info for rules
        has_dairy = False
        has_high_acid = False
        db_ingredients_count = 0
        for i in ingredients:
            ing_name = i.get('name')
            db_ing = Ingredient.objects.filter(name__iexact=ing_name).first()
            if db_ing:
                db_ingredients_count += 1
                # Check Engine Compatibility
                if lab_mode not in db_ing.compatible_systems:
                    audit.append(f"- **Engine Compatibility**: FAIL - '{ing_name}' is not allowed in {lab_mode} (Allowed: {db_ing.compatible_systems}).")
                    status = "FAIL"
                
                # Check Clashing Rules
                if db_ing.ingredient_type == 'DAIRY' or db_ing.category == 'dairy':
                    has_dairy = True
                if db_ing.category == 'citrus' or db_ing.acidity >= 4:
                    has_high_acid = True
                
                # Check Minimum Thresholds
                if db_ing.ingredient_type != 'COFFEE_BEAN' and float(i.get('amount', 0) or 0) < 10.0:
                    audit.append(f"- **Flavor Threshold**: FAIL - '{ing_name}' is below the 10.0 parts minimum ({float(i.get('amount', 0) or 0)} parts).")
                    status = "FAIL"
            else:
                audit.append(f"- **Engine Compatibility**: FAIL - '{ing_name}' not found in database.")
                status = "FAIL"
                
        if db_ingredients_count == len(ingredients) and len(ingredients) > 0:
            audit.append("- **Engine Compatibility**: PASS - All ingredients are registered for this engine.")
            
        # Check Dairy + Acid clash
        if has_dairy and has_high_acid:
            audit.append("- **Mixology Harmony**: FAIL - Suggested dairy combined with high acidity/citrus (curdling risk).")
            status = "FAIL"
        elif len(ingredients) > 0:
            audit.append("- **Mixology Harmony**: PASS - No basic clashing detected.")
            
        if len(ingredients) == 0:
            audit.append("- **Ingredient Count**: FAIL - No ingredients provided.")
            status = "FAIL"
            
        # Build markdown
        md = f"# QA Evaluation Profile\n**Lab Mode:** {lab_mode}\n**Prompt/Scenario:** {name}\n**QA Status:** {status}\n\n"
        
        if not is_suggestion:
            md += f"**Recipe Name:** {data.get('name', 'N/A')}\n"
            md += f"**Description:** {data.get('description', 'N/A')}\n\n"
            
        md += "## Ingredients (AI Generated)\n"
        for i in ingredients:
            ing_name = i.get('name', 'Unknown')
            amt = i.get('amount', 0) or 0
            reason = i.get('reason', '')
            details = f": {amt}% - {reason}" if reason else f": {amt} Parts"
            md += f"- **{ing_name}**{details}\n"
            
        if data.get('reasoning'):
            md += f"\n## AI Mixology Reasoning\n{data.get('reasoning')}\n"
            
        md += "\n## QA Rule Audit\n"
        md += "\n".join(audit) if audit else "- No specific rules evaluated."
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(md)

    def _parse_sse(self, response):
        """Helper to parse SSE stream from StreamingHttpResponse"""
        events = []
        current_event = None
        
        for chunk in response.streaming_content:
            text_chunk = chunk.decode('utf-8')
            lines = text_chunk.split('\n')
            for line in lines:
                line = line.strip()
                if line.startswith('event:'):
                    current_event = line.split('event:', 1)[1].strip()
                elif line.startswith('data:'):
                    data_str = line.split('data:', 1)[1].strip()
                    if current_event and data_str:
                        try:
                            parsed_data = json.loads(data_str)
                            events.append({'event': current_event, 'data': parsed_data})
                        except json.JSONDecodeError:
                            events.append({'event': current_event, 'data': data_str})
        return events

    def test_vibe_creation(self, client):
        self.stdout.write(self.style.MIGRATE_HEADING("\n--- Testing Vibe Creation ---"))
        prompts = [
            "Tropical and fruity",
            "A cozy, warm winter drink",
            "Extremely caffeinated but not bitter"
        ]
        
        for prompt in prompts:
            self.stdout.write(f"\nEvaluating Prompt: '{prompt}'")
            response = client.get(f'/api/ai/vibe-creation/?lab_mode=SODA&prompt={prompt}&mode=standard')
            
            if response.status_code != 200:
                self.stdout.write(self.style.ERROR(f"Failed with status: {response.status_code}"))
                continue
                
            events = self._parse_sse(response)
            recipes = [e['data'] for e in events if e['event'] == 'recipe']
            errors = [e['data'] for e in events if e['event'] == 'error']
            
            if errors:
                self.stdout.write(self.style.ERROR(f"Error returned from stream: {errors}"))
            elif not recipes:
                self.stdout.write(self.style.WARNING("No recipes returned."))
            else:
                for idx, r in enumerate(recipes):
                    self.stdout.write(self.style.SUCCESS(f"  Recipe {idx+1}: {r.get('name')}"))
                    self.stdout.write(f"  Description: {r.get('description', 'N/A')}")
                    for ing in r.get('ingredients', []):
                        self.stdout.write(f"    - {ing.get('name')} ({ing.get('amount')})")
                    self._save_recipe(f"vibe_{idx}", prompt, r, lab_mode="SODA")

    def test_quick_recommendations(self, client):
        self.stdout.write(self.style.MIGRATE_HEADING("\n--- Testing Quick Pick Recommendations ---"))
        drink_types = ['SODA', 'COFFEE']
        
        for dt in drink_types:
            self.stdout.write(f"\nEvaluating Quick Pick for: {dt}")
            response = client.get(f'/api/ai/quick-recommendations/?lab_mode={dt}&mode=standard')
            
            if response.status_code != 200:
                self.stdout.write(self.style.ERROR(f"Failed with status: {response.status_code}"))
                continue
                
            events = self._parse_sse(response)
            recipes = [e['data'] for e in events if e['event'] == 'recipe']
            errors = [e['data'] for e in events if e['event'] == 'error']
            
            if errors:
                self.stdout.write(self.style.ERROR(f"Error returned from stream: {errors}"))
            elif not recipes:
                self.stdout.write(self.style.WARNING("No recipes returned."))
            else:
                for idx, r in enumerate(recipes):
                    self.stdout.write(self.style.SUCCESS(f"  Quick Pick {idx+1}: {r.get('name')}"))
                    for ing in r.get('ingredients', []):
                        self.stdout.write(f"    - {ing.get('name')} ({ing.get('amount')})")
                    self._save_recipe(f"quickpick_{idx}", f"{dt}_quickpick", r, lab_mode=dt)

    def test_ai_suggest(self, client):
        self.stdout.write(self.style.MIGRATE_HEADING("\n--- Testing Manual Builder Suggestion Copilot ---"))
        
        scenarios = [
            {"ingredients": [], "drink_type": "SODA", "desc": "Empty state (Should suggest a Base)"},
            {"ingredients": ["Cold Brew Coffee"], "drink_type": "COFFEE", "desc": "Has Cold Brew (Should suggest a milk/syrup)"}
        ]
        
        for idx, sc in enumerate(scenarios):
            self.stdout.write(f"\nEvaluating Suggestion Scenario: {sc['desc']}")
            payload = {
                "ingredients": sc["ingredients"],
                "drink_type": sc["drink_type"],
                "mode": "standard"
            }
            
            response = client.post(
                '/api/ai/suggest/',
                data=json.dumps(payload),
                content_type='application/json'
            )
            
            if response.status_code != 200:
                self.stdout.write(self.style.ERROR(f"Failed with status: {response.status_code}"))
                continue
                
            events = self._parse_sse(response)
            
            json_events = [e['data'] for e in events if e['event'] == 'json']
            
            if not json_events:
                self.stdout.write(self.style.WARNING("No suggestion JSON events returned."))
            else:
                for json_data in json_events:
                    if json_data.get('status') == 'success':
                        suggestions = json_data.get('suggestions', [])
                        self.stdout.write(self.style.SUCCESS(f"  Got {len(suggestions)} suggestions:"))
                        for sug in suggestions:
                            reason = sug.get('reason', 'N/A')
                            self.stdout.write(f"    - {sug.get('name')} (Reason: {reason})")
                        self._save_recipe(f"copilot_{idx}", sc['desc'], json_data, lab_mode=sc['drink_type'])
                    elif json_data.get('status') == 'error':
                        self.stdout.write(self.style.ERROR(f"  Error: {json_data.get('message')}"))
