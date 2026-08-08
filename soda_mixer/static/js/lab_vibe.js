const currentLabMode = window.CURRENT_LAB;

console.log('ðŸŽ¨ VIBE CREATOR SUBSTRATE LOADED');

let vibeDrinkSource = null;

function generateVibeDrink() {
        const btn = document.getElementById('btnGenerateVibe');
        const input = document.getElementById('vibePromptInput');
        const prompt = input.value.trim();
        const list = document.getElementById('vibeDrinkResult');
        
        if (!prompt) {
            alert('Please enter a description or vibe.');
            return;
        }
        
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';
        list.innerHTML = '';
        
        if (vibeDrinkSource) { vibeDrinkSource.close(); }
        
        const params = new URLSearchParams({ lab_mode: currentLabMode, prompt: prompt, mode: window.recommendationMode || 'standard' });
        vibeDrinkSource = new EventSource(`/api/ai/vibe-creation/?${params.toString()}`);
        
        let currentCard = null;
        let currentIngredients = null;
        
        vibeDrinkSource.addEventListener('recipe', (e) => {
            const recipe = JSON.parse(e.data);
            
            let badgesHtml = '';
            const mappedIds = [];
            if (recipe.ingredients && Array.isArray(recipe.ingredients)) {
                recipe.ingredients.forEach(ing => {
                    let matchedId = null;
                    let matchedCategory = null;
                    const dataScript = document.getElementById('ingredients-data');
                    if (dataScript) {
                        try {
                            const allIngredients = JSON.parse(dataScript.textContent);
                            const cleanName = ing.name.replace(/\s*[\[\(].*?[\]\)]\s*/g, '').trim().toLowerCase();
                            for (let dbIng of allIngredients) {
                                const dbCleanName = dbIng.name.replace(/\s*[\[\(].*?[\]\)]\s*/g, '').trim().toLowerCase();
                                if (dbCleanName === cleanName) {
                                    matchedId = dbIng.id;
                                    matchedCategory = dbIng.category;
                                    break;
                                }
                            }
                        } catch(e) {
                            console.error("Error parsing ingredients data", e);
                        }
                    }
                    if (matchedCategory) {
                        badgesHtml += `<span class="badge border border-white border-opacity-10 text-white fw-normal px-2 py-1"><span class="me-1">${ing.name}</span><span class="badge-fizz bg-${matchedCategory.toLowerCase().trim()} opacity-75" style="font-size: 0.55rem; padding: 0.15rem 0.3rem;">${matchedCategory.toUpperCase()}</span></span>`;
                    } else {
                        badgesHtml += `<span class="badge border border-white border-opacity-10 text-white fw-normal px-2 py-1">${ing.name}</span>`;
                    }
                    
                    if (matchedId) {
                        mappedIds.push({id: matchedId, name: ing.name, amount: ing.amount});
                    } else {
                        mappedIds.push({name: ing.name, amount: ing.amount});
                    }
                });
            }
            
            currentCard = document.createElement('div');
            currentCard.className = 'glass-card p-3 mb-3 animate-fade-in border-white border-opacity-10';
            currentCard.innerHTML = `
                <div class="d-flex justify-content-between align-items-start mb-2">
                    <h5 class="fw-bold text-lab-accent mb-0" id="vibe-name">${recipe.name}</h5>
                    <div>
                        <button type="button" class="btn btn-sm btn-outline-warning px-3 me-2" onclick="tryAgainVibe('${prompt.replace(/'/g, "\\'")}')" id="vibe-retry">
                            <i class="bi bi-arrow-clockwise me-1"></i> TRY AGAIN
                        </button>
                        <button type="button" class="btn btn-sm btn-outline-experimental px-3" onclick="selectGeneratedDrink(this)" id="vibe-select">
                            <i class="bi bi-check2-circle me-1"></i> SELECT
                        </button>
                    </div>
                </div>
                <p class="text-dim mb-3" id="vibe-desc">${recipe.description || ''}</p>
                <div class="small d-flex align-items-center flex-wrap gap-2">
                    <strong class="text-dim mb-0">Ingredients:</strong>
                    <div id="vibe-ingredients" class="d-flex flex-wrap gap-1">
                        ${badgesHtml}
                    </div>
                </div>
                <div id="vibe-data" style="display: none;">${JSON.stringify(mappedIds)}</div>
            `;
            
            list.appendChild(currentCard);
        });
        
        vibeDrinkSource.addEventListener('error', (e) => {
            console.error("SSE Event Error:", e);
        });
        
        vibeDrinkSource.addEventListener('close', () => {
            btn.disabled = false;
            btn.innerHTML = '<i class="bi bi-magic me-1"></i> SUBMIT';
            vibeDrinkSource.close();
            vibeDrinkSource = null;
        });
        
        vibeDrinkSource.onerror = (err) => {
            console.error("SSE Error:", err);
            btn.disabled = false;
            btn.innerHTML = 'Error - Try Again';
            vibeDrinkSource.close();
            vibeDrinkSource = null;
        };
    }





function selectGeneratedDrink(btnElement) {
        const card = btnElement.closest('.glass-card');
        const dataDiv = card.querySelector('div[id^="drink-data-"], div[id="vibe-data"]');
        const nameEl = card.querySelector('h5[id^="drink-name-"], h5[id="vibe-name"]');
        
        if (!dataDiv) return;
        
        let ingredientData = [];
        try {
            ingredientData = JSON.parse(dataDiv.textContent);
        } catch (e) {
            console.error("Failed to parse ingredient data:", e);
            return;
        }

        const recipeName = nameEl ? nameEl.textContent.trim() : "Generated Drink";

        const recipeData = {
            name: recipeName,
            drink_type: currentLabMode,
            coffee_style: "",
            coffee_base_type: "",
            drink_size_oz: 12,
            ingredients: ingredientData
        };

        const form = document.createElement('form');
        form.method = 'POST';
        form.action = '/lab/synopsis/';
        
        const csrfInput = document.createElement('input');
        csrfInput.type = 'hidden';
        csrfInput.name = 'csrfmiddlewaretoken';
        csrfInput.value = window.CSRF_TOKEN;
        form.appendChild(csrfInput);

        const dataInput = document.createElement('input');
        dataInput.type = 'hidden';
        dataInput.name = 'recipe_data';
        dataInput.value = JSON.stringify(recipeData);
        form.appendChild(dataInput);

        document.body.appendChild(form);
        form.submit();
    }



document.addEventListener('DOMContentLoaded', () => {
    const savedRecMode = localStorage.getItem('recommendation_mode') || 'standard';
    try { setRecommendationMode(savedRecMode); } catch(e) {}
    
    const vibeInput = document.getElementById('vibePromptInput');
    if (vibeInput) {
        vibeInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                generateVibeDrink();
            }
        });
    }
});

function setRecommendationMode(mode) {
    window.recommendationMode = mode;
    localStorage.setItem('recommendation_mode', mode);
    try {
        const stdBtn = document.getElementById('toggleStandard');
        const expBtn = document.getElementById('toggleExperimental');
        if (mode === 'experimental') {
            if (stdBtn) { stdBtn.classList.remove('active-lab-mode'); stdBtn.classList.add('text-dim'); }
            if (expBtn) { expBtn.classList.add('active-lab-mode'); expBtn.classList.remove('text-dim'); }
        } else {
            if (expBtn) { expBtn.classList.remove('active-lab-mode'); expBtn.classList.add('text-dim'); }
            if (stdBtn) { stdBtn.classList.add('active-lab-mode'); stdBtn.classList.remove('text-dim'); }
        }
    } catch(e) {}
}

window.tryAgainVibe = function(prompt) {
    document.getElementById('vibePromptInput').value = prompt;
    generateVibeDrink();
};
