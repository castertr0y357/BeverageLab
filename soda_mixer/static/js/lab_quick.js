// Quick Drinks Generation and Selection Logic
const currentLabMode = window.CURRENT_LAB || "soda";

function generateQuickRecommendations() {
    console.log("⚡ QUICK DRINKS SUBSTRATE LOADED");
    
    // Stop any ongoing generation
    if (window.quickDrinksSource) {
        window.quickDrinksSource.close();
        window.quickDrinksSource = null;
    }

    const list = document.getElementById('quickDrinksList');
    const btn = document.getElementById('btnGenerateQuick');
    if (!list) return;

    if (btn) btn.style.display = 'none';

    list.innerHTML = `
        <div id="quickDrinksProgress" class="col-12 text-center py-5 opacity-75">
            <div class="spinner-border text-lab-accent mb-4" role="status" style="width: 3rem; height: 3rem;">
                <span class="visually-hidden">Loading...</span>
            </div>
            <p id="quickDrinksProgressText" class="mb-0 small fw-bold text-dim animate-pulse">COMPUTING MOLECULAR AFFINITY...</p>
        </div>
    `;

    const params = new URLSearchParams({ lab_mode: currentLabMode, mode: window.recommendationMode || 'standard' });
    const url = `/api/ai/quick-recommendations/?${params.toString()}`;
    
    let quickDrinksSource = new EventSource(url);
    window.quickDrinksSource = quickDrinksSource;
    
    let currentIngredients = null;
    
    quickDrinksSource.addEventListener('recipe', (e) => {
        const recipe = JSON.parse(e.data);
        const index = recipe.index;
        
        const currentCard = document.createElement('div');
        currentCard.className = 'glass-card p-3 mb-3 animate-fade-in border-white border-opacity-10';
        
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
                        console.log(`[Quick Drink] Processing ingredient: "${ing.name}" (Clean: "${cleanName}")`);
                        
                        for (let dbIng of allIngredients) {
                            const dbCleanName = dbIng.name.replace(/\s*[\[\(].*?[\]\)]\s*/g, '').trim().toLowerCase();
                            if (dbCleanName === cleanName) {
                                matchedId = dbIng.id;
                                matchedCategory = dbIng.category;
                                console.log(`[Quick Drink] MATCH FOUND: DB Name="${dbIng.name}", ID=${matchedId}, Category=${matchedCategory}`);
                                break;
                            }
                        }
                        if (!matchedId) {
                            console.warn(`[Quick Drink] NO MATCH for "${ing.name}" in database of ${allIngredients.length} items`);
                        }
                    } catch(e) {
                        console.error("[Quick Drink] Error parsing ingredients data", e);
                    }
                } else {
                    console.error("[Quick Drink] FATAL: 'ingredients-data' script element not found in DOM!");
                }
                
                if (matchedCategory) {
                    badgesHtml += `<div class="badge border border-white border-opacity-10 text-white fw-normal p-2 d-inline-flex flex-column align-items-center gap-1" style="background: rgba(255,255,255,0.03); min-width: 80px;">
                        <span style="font-size: 0.85rem;">${ing.name}</span>
                        <span class="badge-fizz bg-${matchedCategory.toLowerCase().trim()} opacity-75 w-100 text-center" style="font-size: 0.6rem; padding: 0.2rem 0.4rem; border-radius: 4px; letter-spacing: 0.5px;">${matchedCategory.toUpperCase()}</span>
                    </div>`;
                } else {
                    badgesHtml += `<div class="badge border border-white border-opacity-10 text-white fw-normal p-2 d-inline-flex align-items-center justify-content-center" style="background: rgba(255,255,255,0.03); min-width: 80px;">
                        <span style="font-size: 0.85rem;">${ing.name}</span>
                    </div>`;
                }
                
                if (matchedId) {
                    mappedIds.push({id: matchedId, name: ing.name, amount: ing.amount});
                } else {
                    mappedIds.push({name: ing.name, amount: ing.amount});
                    console.warn(`[Drinks Match] WARNING: No card found for "${ing.name}"`);
                }
            });
        }
        
        currentCard.innerHTML = `
            <div class="d-flex justify-content-between align-items-start mb-2">
                <h5 class="fw-bold text-lab-accent mb-0" id="drink-name-${index}">${recipe.name}</h5>
                <button type="button" class="btn btn-sm btn-outline-experimental px-3" onclick="selectGeneratedDrink(this)" id="drink-select-${index}">
                    <i class="bi bi-check2-circle me-1"></i> SELECT
                </button>
            </div>
            <p class="text-white opacity-90 small mb-2" id="drink-desc-${index}">${recipe.description || ''}</p>
            <div class="small d-flex align-items-center flex-wrap gap-2">
                <strong class="text-dim mb-0">Ingredients:</strong>
                <div id="drink-ingredients-${index}" class="d-flex flex-wrap gap-1">
                    ${badgesHtml}
                </div>
            </div>
            <div id="drink-data-${index}" style="display: none;">${JSON.stringify(mappedIds)}</div>
        `;
        
        const ph = document.getElementById(`quickDrinksProgress`);
        if (ph) {
            list.replaceChild(currentCard, ph);
        } else {
            list.appendChild(currentCard);
        }
    });

    quickDrinksSource.addEventListener('done', () => {
        quickDrinksSource.close();
        const ph = document.getElementById(`quickDrinksProgress`);
        if (ph) ph.remove();
        if (btn) btn.style.display = 'inline-block';
        window.quickDrinksSource = null;
    });

    quickDrinksSource.addEventListener('error', (e) => {
        quickDrinksSource.close();
        const ph = document.getElementById(`quickDrinksProgress`);
        if (ph) {
            ph.innerHTML = `<div class="text-danger"><i class="bi bi-exclamation-triangle"></i> Synthesis interruption detected.</div>`;
        }
        if (btn) btn.style.display = 'inline-block';
        window.quickDrinksSource = null;
    });
}

function selectGeneratedDrink(btnElement) {
    const card = btnElement.closest('.glass-card');
    const dataDiv = card.querySelector('div[id^="drink-data-"]');
    const nameEl = card.querySelector('h5[id^="drink-name-"]');
    
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
        drink_type: currentLabMode, // Use dynamic currentLabMode
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
    csrfInput.value = window.CSRF_TOKEN || document.cookie.split('; ').find(row => row.startsWith('csrftoken=')).split('=')[1];
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
    
    const list = document.getElementById('quickDrinksList');
    if (list && list.children.length === 0) {
        generateQuickRecommendations();
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
    
    // Regenerate recommendations with new mode if the list is already populated
    const list = document.getElementById('quickDrinksList');
    if (list && list.children.length > 0) {
        generateQuickRecommendations();
    }
}
