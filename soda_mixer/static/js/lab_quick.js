// Quick Drinks Unified Vault & Cycle Logic (Existing Saved Recipes + Nightly Cached AI Pool)
const currentLabMode = window.CURRENT_LAB || "soda";
window.currentProfile = null;
window.currentProfileDisplay = null;
window.seenQuickDrinkIds = new Set();

function selectProfile(profile, displayTitle = null) {
    window.currentProfile = profile;
    window.currentProfileDisplay = displayTitle || profile.replace(/^holiday:/i, '').replace(/-/g, ' ');
    window.seenQuickDrinkIds = new Set();
    const profilesContainer = document.getElementById('quickProfilesContainer');
    const aiContainer = document.getElementById('aiQuickContainer');

    if (profilesContainer) profilesContainer.style.display = 'none';
    if (aiContainer) aiContainer.style.display = 'block';

    drawQuickDrinksFromPool(profile);
}

function drawQuickDrinksFromPool(profile) {
    const existingCatName = document.getElementById('existingRecipeCategoryName');
    const aiCatName = document.getElementById('aiRecipeCategoryName');
    const btnCycle = document.getElementById('btnShuffleExisting');
    const btnLive = document.getElementById('btnGenerateQuick');
    const list = document.getElementById('quickDrinksList');
    const subtext = document.getElementById('quickDrinksPoolSubtext');

    const labelText = window.currentProfileDisplay || profile;
    if (existingCatName) existingCatName.innerText = labelText;
    if (aiCatName) aiCatName.innerText = labelText;

    const params = new URLSearchParams({
        lab_mode: currentLabMode,
        profile: profile,
        mode: window.recommendationMode || 'experimental',
        exclude_ids: Array.from(window.seenQuickDrinkIds).join(','),
        count: '5'
    });

    fetch(`/api/quick-drinks/draw/?${params.toString()}`)
        .then(r => r.json())
        .then(data => {
            if (data.status === 'success' && !data.needs_live_generation && data.items && data.items.length > 0) {
                if (data.cycle_wrapped) {
                    window.seenQuickDrinkIds = new Set();
                }
                data.items.forEach(item => window.seenQuickDrinkIds.add(item.id));

                if (list) list.innerHTML = '';
                data.items.forEach((item, idx) => {
                    const card = buildQuickDrinkCard(item, idx);
                    if (list) list.appendChild(card);
                });

                if (btnCycle) {
                    btnCycle.style.display = data.total_pool_size > 5 ? 'inline-block' : 'none';
                }
                if (btnLive) {
                    btnLive.style.display = 'none';
                }
                if (subtext) {
                    subtext.innerText = `Showing ${data.items.length} of ${data.total_pool_size} ready formulas across complexity tiers.`;
                }
            } else {
                // Pool is completely empty for this category -> fallback to live LLM generation
                if (btnCycle) btnCycle.style.display = 'none';
                generateQuickRecommendations();
            }
        })
        .catch(err => {
            console.error('Error drawing from Quick Drinks pool:', err);
            generateQuickRecommendations();
        });
}

function cycleQuickDrinks() {
    if (window.currentProfile) {
        drawQuickDrinksFromPool(window.currentProfile);
    }
}

// Keep compatibility alias
function shuffleExistingRecipes() {
    cycleQuickDrinks();
}

function resolveIngredientsWithDomMetadata(rawIngredients) {
    let badgesHtml = '';
    const mappedIds = [];
    const dataScript = document.getElementById('ingredients-data');
    let allIngredients = [];
    if (dataScript) {
        try {
            allIngredients = JSON.parse(dataScript.textContent);
        } catch (e) {
            console.error("[Quick Drink] Error parsing ingredients-data:", e);
        }
    }

    (rawIngredients || []).forEach(ing => {
        let matchedId = ing.id || null;
        let matchedCategory = ing.category || null;
        let matchedDbIng = null;

        const cleanNameRaw = (ing.name || '').replace(/\s*[\[\(].*?[\]\)]\s*/g, '').trim();
        const cleanName = cleanNameRaw.toLowerCase();
        for (let dbIng of allIngredients) {
            const dbCleanName = (dbIng.name || '').replace(/\s*[\[\(].*?[\]\)]\s*/g, '').trim().toLowerCase();
            if ((matchedId && dbIng.id === matchedId) || dbCleanName === cleanName) {
                matchedId = dbIng.id;
                matchedCategory = dbIng.category;
                matchedDbIng = dbIng;
                break;
            }
        }

        const displayName = matchedDbIng ? matchedDbIng.name : cleanNameRaw;

        if (matchedCategory) {
            badgesHtml += `<div class="badge border border-white border-opacity-10 text-white fw-normal p-2 d-inline-flex flex-column align-items-center gap-1" style="background: rgba(255,255,255,0.03); min-width: 80px;">
                <span style="font-size: 0.85rem;">${displayName}</span>
                <span class="badge-fizz bg-${matchedCategory.toLowerCase().trim()} opacity-75 w-100 text-center" style="font-size: 0.6rem; padding: 0.2rem 0.4rem; border-radius: 4px; letter-spacing: 0.5px;">${matchedCategory.toUpperCase()}</span>
            </div>`;
        } else {
            badgesHtml += `<div class="badge border border-white border-opacity-10 text-white fw-normal p-2 d-inline-flex align-items-center justify-content-center" style="background: rgba(255,255,255,0.03); min-width: 80px;">
                <span style="font-size: 0.85rem;">${displayName}</span>
            </div>`;
        }

        const amountVal = ing.amount !== undefined ? ing.amount : (ing.parts !== undefined ? ing.parts : 15.0);
        if (matchedId && matchedDbIng) {
            mappedIds.push({
                id: matchedId,
                name: matchedDbIng.name,
                amount: amountVal,
                is_primary: !!ing.is_primary,
                isPrimary: !!ing.is_primary,
                type: matchedDbIng.ingredient_type || matchedDbIng.type,
                physical_state: matchedDbIng.physical_state,
                mixology_function: matchedDbIng.mixology_function,
                category: matchedDbIng.category,
                intensity: matchedDbIng.intensity,
                sweetness: matchedDbIng.sweetness,
                acidity: matchedDbIng.acidity,
                bitterness: matchedDbIng.bitterness
            });
        } else {
            mappedIds.push({
                id: matchedId,
                name: displayName,
                amount: amountVal,
                is_primary: !!ing.is_primary,
                isPrimary: !!ing.is_primary,
                category: matchedCategory
            });
        }
    });

    return { badgesHtml, mappedIds };
}

function buildQuickDrinkCard(item, index) {
    const currentCard = document.createElement('div');
    currentCard.className = 'glass-card p-3 mb-2 animate-fade-in border-white border-opacity-10';
    currentCard.dataset.drinkUuid = item.uuid || '';
    currentCard.dataset.sourceType = item.source_type || 'cached';

    const { badgesHtml, mappedIds } = resolveIngredientsWithDomMetadata(item.ingredients || []);

    const isExisting = item.source_type === 'existing';
    let statusBadgeHtml = '';
    if (isExisting) {
        const stars = item.rating > 0 ? `<span class="text-warning small me-1">${'★'.repeat(item.rating)}${'☆'.repeat(5 - item.rating)}</span>` : '';
        statusBadgeHtml = `${stars}<span class="badge bg-success bg-opacity-25 text-success border border-success border-opacity-25" style="font-size: 0.65rem;">EXISTING RECIPE</span>`;
    } else {
        statusBadgeHtml = `<span class="badge bg-info bg-opacity-10 text-info border border-info border-opacity-25" style="font-size: 0.65rem;">CACHED AI • ${(item.ingredients || []).length} ING</span>`;
    }

    let actionButtonsHtml = '';
    if (isExisting) {
        actionButtonsHtml = `
            <a href="/recipes/${item.uuid}/" class="btn btn-sm btn-outline-primary px-3 py-1 fw-bold text-white">
                <i class="bi bi-eye me-1"></i> View Formula
            </a>
        `;
    } else {
        const dismissBtn = item.uuid ? `
            <button type="button" class="btn btn-sm btn-outline-danger border-0 px-2 py-1" onclick="dismissCachedDrink('${item.uuid}', this)" title="Dismiss from cache so nightly job replaces it">
                <i class="bi bi-x-lg"></i>
            </button>
        ` : '';
        actionButtonsHtml = `
            <div class="d-flex align-items-center gap-1">
                <button type="button" class="btn btn-sm btn-outline-experimental px-3" onclick="selectGeneratedDrink(this)" id="drink-select-${index}">
                    <i class="bi bi-check2-circle me-1"></i> SELECT
                </button>
                ${dismissBtn}
            </div>
        `;
    }

    const metaPayload = {
        cached_uuid: item.source_type === 'cached' ? (item.uuid || item.cached_uuid || null) : null,
        holiday_theme_id: item.holiday_theme_id || null,
        description: item.description || '',
        mixologist_notes: item.mixologist_notes || '',
        profile_description: item.profile_description || ''
    };

    currentCard.innerHTML = `
        <div class="d-flex justify-content-between align-items-start mb-2 gap-2 flex-wrap">
            <div class="d-flex align-items-center gap-2 flex-wrap">
                <h5 class="fw-bold text-lab-accent mb-0" id="drink-name-${index}">${item.name}</h5>
                ${statusBadgeHtml}
            </div>
            ${actionButtonsHtml}
        </div>
        <p class="text-white opacity-90 small mb-2" id="drink-desc-${index}">${item.description || ''}</p>
        <div class="small d-flex align-items-center flex-wrap gap-2">
            <strong class="text-dim mb-0">Ingredients:</strong>
            <div id="drink-ingredients-${index}" class="d-flex flex-wrap gap-1">
                ${badgesHtml}
            </div>
        </div>
        <div id="drink-data-${index}" style="display: none;">${JSON.stringify(mappedIds)}</div>
        <div id="drink-meta-${index}" style="display: none;">${JSON.stringify(metaPayload)}</div>
    `;

    return currentCard;
}

function dismissCachedDrink(uuid, btnEl) {
    if (!uuid || !btnEl) return;
    btnEl.disabled = true;
    btnEl.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';

    const card = btnEl.closest('.glass-card');
    const csrfToken = window.CSRF_TOKEN || (document.cookie.split('; ').find(row => row.startsWith('csrftoken=')) || '').split('=')[1];

    fetch(`/api/quick-drinks/${uuid}/dismiss/`, {
        method: 'POST',
        headers: { 'X-CSRFToken': csrfToken }
    })
    .then(r => r.json())
    .then(data => {
        if (data.status === 'dismissed') {
            // Try drawing 1 unseen replacement card to slide into place
            const params = new URLSearchParams({
                lab_mode: currentLabMode,
                profile: window.currentProfile || '',
                mode: window.recommendationMode || 'experimental',
                exclude_ids: Array.from(window.seenQuickDrinkIds).join(','),
                count: '1'
            });
            fetch(`/api/quick-drinks/draw/?${params.toString()}`)
                .then(res => res.json())
                .then(drawData => {
                    if (drawData.status === 'success' && drawData.items && drawData.items.length > 0 && !drawData.cycle_wrapped) {
                        const replacement = drawData.items[0];
                        window.seenQuickDrinkIds.add(replacement.id);
                        const newCard = buildQuickDrinkCard(replacement, Math.floor(Math.random() * 1000));
                        if (card && card.parentNode) {
                            card.parentNode.replaceChild(newCard, card);
                            return;
                        }
                    }
                    if (card) card.remove();
                })
                .catch(() => {
                    if (card) card.remove();
                });
        } else {
            btnEl.disabled = false;
            btnEl.innerHTML = '<i class="bi bi-x-lg"></i>';
        }
    })
    .catch(err => {
        console.error('Error dismissing cached drink:', err);
        btnEl.disabled = false;
        btnEl.innerHTML = '<i class="bi bi-x-lg"></i>';
    });
}

function resetToProfiles() {
    window.currentProfile = null;
    window.seenQuickDrinkIds = new Set();
    const profilesContainer = document.getElementById('quickProfilesContainer');
    const aiContainer = document.getElementById('aiQuickContainer');
    const list = document.getElementById('quickDrinksList');

    if (window.quickDrinksSource) {
        window.quickDrinksSource.close();
        window.quickDrinksSource = null;
    }

    if (list) list.innerHTML = '';
    if (aiContainer) aiContainer.style.display = 'none';
    if (profilesContainer) profilesContainer.style.display = 'block';
}

function generateQuickRecommendations() {
    console.log("⚡ EMPTY POOL FALLBACK: STREAMING QUICK DRINKS LIVE");

    if (window.quickDrinksSource) {
        window.quickDrinksSource.close();
        window.quickDrinksSource = null;
    }

    const list = document.getElementById('quickDrinksList');
    const btn = document.getElementById('btnGenerateQuick');
    const subtext = document.getElementById('quickDrinksPoolSubtext');
    if (!list) return;

    if (btn) btn.style.display = 'none';
    if (subtext) subtext.innerText = 'Cache empty for this category — synthesizing fresh formulas on the fly...';

    list.innerHTML = `
        <div id="quickDrinksProgress" class="col-12 text-center py-5 opacity-75">
            <div class="spinner-border text-lab-accent mb-4" role="status" style="width: 3rem; height: 3rem;">
                <span class="visually-hidden">Loading...</span>
            </div>
            <p id="quickDrinksProgressText" class="mb-0 small fw-bold text-dim animate-pulse">COMPUTING MOLECULAR AFFINITY...</p>
        </div>
    `;

    const params = new URLSearchParams({ lab_mode: currentLabMode, mode: window.recommendationMode || 'experimental' });
    if (window.currentProfile) {
        params.append('profile', window.currentProfile);
    }
    const url = `/api/ai/quick-recommendations/?${params.toString()}`;

    let quickDrinksSource = new EventSource(url);
    window.quickDrinksSource = quickDrinksSource;

    quickDrinksSource.addEventListener('recipe', (e) => {
        const recipe = JSON.parse(e.data);
        const index = recipe.index;
        recipe.source_type = 'cached';
        recipe.uuid = recipe.cached_uuid || '';
        const currentCard = buildQuickDrinkCard(recipe, index);

        const ph = document.getElementById(`quickDrinksProgress`);
        if (ph) {
            list.replaceChild(currentCard, ph);
        } else {
            list.appendChild(currentCard);
        }
    });

    quickDrinksSource.addEventListener('close', () => {
        quickDrinksSource.close();
        const ph = document.getElementById(`quickDrinksProgress`);
        if (ph) ph.remove();
        window.quickDrinksSource = null;
    });

    quickDrinksSource.addEventListener('done', () => {
        quickDrinksSource.close();
        const ph = document.getElementById(`quickDrinksProgress`);
        if (ph) ph.remove();
        window.quickDrinksSource = null;
    });

    quickDrinksSource.addEventListener('error', () => {
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
    const metaDiv = card.querySelector('div[id^="drink-meta-"]');
    const nameEl = card.querySelector('h5[id^="drink-name-"]');

    if (!dataDiv) return;

    let ingredientData = [];
    let metaData = {};
    try {
        ingredientData = JSON.parse(dataDiv.textContent);
        if (metaDiv && metaDiv.textContent) {
            metaData = JSON.parse(metaDiv.textContent);
        }
    } catch (e) {
        console.error("Failed to parse ingredient data:", e);
        return;
    }

    const recipeName = nameEl ? nameEl.textContent.trim() : "Generated Drink";
    const hasPrecomputedNotes = !!(metaData.mixologist_notes || metaData.profile_description);

    const recipeData = {
        name: recipeName,
        description: metaData.description || '',
        mixologist_notes: metaData.mixologist_notes || '',
        profile_description: metaData.profile_description || '',
        skip_ai: hasPrecomputedNotes,
        source_cached_drink_id: metaData.cached_uuid || null,
        holiday_theme_id: metaData.holiday_theme_id || null,
        drink_type: currentLabMode,
        coffee_style: (currentLabMode === "COFFEE" || currentLabMode === "coffee") ? "HOT" : "",
        coffee_base_type: (currentLabMode === "COFFEE" || currentLabMode === "coffee") ? "ESPRESSO" : "",
        drink_size_oz: 12,
        ingredients: ingredientData
    };

    const form = document.createElement('form');
    form.method = 'POST';
    form.action = '/lab/synopsis/';

    const csrfInput = document.createElement('input');
    csrfInput.type = 'hidden';
    csrfInput.name = 'csrfmiddlewaretoken';
    csrfInput.value = window.CSRF_TOKEN || (document.cookie.split('; ').find(row => row.startsWith('csrftoken=')) || '').split('=')[1];
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
    const savedRecMode = localStorage.getItem('recommendation_mode') || 'experimental';
    try { setRecommendationMode(savedRecMode); } catch(e) {}
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

    const aiContainer = document.getElementById('aiQuickContainer');
    if (window.currentProfile && aiContainer && aiContainer.style.display !== 'none') {
        window.seenQuickDrinkIds = new Set();
        drawQuickDrinksFromPool(window.currentProfile);
    }
}
