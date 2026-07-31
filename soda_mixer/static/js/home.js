    // ==========================================
// 1. STATE & GLOBAL VARIABLES
// ==========================================
let currentLabMode = 'SODA';
    let recommendationMode = 'standard';
    let selectedIngredients = []; 
        let bottleScale = 1.0; 
    let latestCoffeeChemistryData = null;
    let latestSodaChemistryData = null;
    let latestCryoChemistryData = null;
    let sodaSweetnessStyle = localStorage.getItem('soda_sweetness_style') || 'CRAFT';
    let currentStepKey = '';
    let stepExcludingIds = [];
    let stepExcludingNames = [];

    
// ==========================================
// 2. CHEMISTRY & CALCULATIONS
// ==========================================
function getChemistryAlignedIngredient(ing, idx) {
        if (!latestCoffeeChemistryData || !latestCoffeeChemistryData.ingredients) {
            return null;
        }
        
        const type = (ing.type || ing.ingredient_type || '').toUpperCase();
        
        let itypeCategory = 'modifier';
        if (type === 'COFFEE_BEAN') {
            itypeCategory = 'coffee';
        } else if (type === 'DAIRY') {
            const firstDairyIdx = selectedIngredients.findIndex(x => (x.type || x.ingredient_type || '').toUpperCase() === 'DAIRY');
            if (idx === firstDairyIdx) {
                itypeCategory = 'dairy';
            } else {
                itypeCategory = 'modifier';
            }
        } else if (type === 'ADDITIVE' || type === 'OTHER' || type === 'SODA_SYRUP') {
            itypeCategory = 'modifier';
        } else {
            const nameLower = (ing.name || '').toLowerCase();
            if (nameLower.includes('milk') || nameLower.includes('oat') || nameLower.includes('almond') || nameLower.includes('soy') || nameLower.includes('dairy')) {
                itypeCategory = 'dairy';
            } else if (nameLower.includes('syrup') || nameLower.includes('sauce') || nameLower.includes('honey') || nameLower.includes('sugar')) {
                itypeCategory = 'modifier';
            } else {
                itypeCategory = 'modifier';
            }
        }
        
        let countInCat = 0;
        for (let i = 0; i < idx; i++) {
            const otherIng = selectedIngredients[i];
            const otherType = (otherIng.type || otherIng.ingredient_type || '').toUpperCase();
            let otherCat = 'modifier';
            if (otherType === 'COFFEE_BEAN') {
                otherCat = 'coffee';
            } else if (otherType === 'DAIRY') {
                otherCat = 'dairy';
            } else if (otherType === 'ADDITIVE' || otherType === 'OTHER' || otherType === 'SODA_SYRUP') {
                otherCat = 'modifier';
            } else {
                const otherNameLower = (otherIng.name || '').toLowerCase();
                if (otherNameLower.includes('milk') || otherNameLower.includes('oat') || otherNameLower.includes('almond') || otherNameLower.includes('soy') || otherNameLower.includes('dairy')) {
                    otherCat = 'dairy';
                } else if (otherNameLower.includes('syrup') || otherNameLower.includes('sauce') || otherNameLower.includes('honey') || otherNameLower.includes('sugar')) {
                    otherCat = 'modifier';
                } else {
                    otherCat = 'modifier';
                }
            }
            if (otherCat === itypeCategory) {
                countInCat++;
            }
        }
        
        if (itypeCategory === 'coffee') {
            const mix = latestCoffeeChemistryData.ingredients.coffee_base_mix || [];
            const matchedMix = mix.find(x => x.id == ing.id);
            if (matchedMix) {
                const budget = latestCoffeeChemistryData.drink_metrics.total_liquid_budget_oz || 1.0;
                const pct = budget > 0 ? ((matchedMix.volume_oz / budget) * 100).toFixed(1) : '0';
                return {
                    name: matchedMix.name,
                    volume_oz: matchedMix.volume_oz,
                    percentage_of_liquid: pct
                };
            }
            const cb = latestCoffeeChemistryData.ingredients.coffee_base;
            if (cb) {
                const coffeeBeans = selectedIngredients.filter(x => (x.type || x.ingredient_type || '').toUpperCase() === 'COFFEE_BEAN');
                const totalAmt = coffeeBeans.reduce((sum, x) => sum + parseFloat(x.amount || 0), 0);
                const thisAmt = parseFloat(ing.amount || 0);
                const ratio = totalAmt > 0 ? (thisAmt / totalAmt) : 1.0;
                const budget = latestCoffeeChemistryData.drink_metrics.total_liquid_budget_oz || 1.0;
                const pct = budget > 0 ? (((cb.volume_oz * ratio) / budget) * 100).toFixed(1) : '0';
                return {
                    name: cb.name,
                    volume_oz: cb.volume_oz * ratio,
                    percentage_of_liquid: pct
                };
            }
        } else if (itypeCategory === 'dairy') {
            const pf = latestCoffeeChemistryData.ingredients.payload_filler;
            if (pf && pf.name !== 'None') {
                if (pf.id == ing.id || countInCat === 0) {
                    const budget = latestCoffeeChemistryData.drink_metrics.total_liquid_budget_oz || 1.0;
                    const pct = budget > 0 ? ((pf.volume_oz / budget) * 100).toFixed(1) : '0';
                    return {
                        name: pf.name,
                        volume_oz: pf.volume_oz,
                        percentage_of_liquid: pct,
                        is_corrected: pf.is_corrected || false,
                        primary_name: pf.primary_name || '',
                        primary_volume_oz: pf.primary_volume_oz || 0,
                        texturizer_name: pf.texturizer_name || '',
                        texturizer_volume_oz: pf.texturizer_volume_oz || 0
                    };
                }
            }
        } else if (itypeCategory === 'modifier') {
            const list = latestCoffeeChemistryData.ingredients.flavor_modifiers || [];
            const matchedFm = list.find(fm => fm.id == ing.id);
            if (matchedFm) {
                const budget = latestCoffeeChemistryData.drink_metrics.total_liquid_budget_oz || 1.0;
                const pct = budget > 0 ? ((matchedFm.volume_oz / budget) * 100).toFixed(1) : '0';
                return {
                    name: matchedFm.name,
                    volume_oz: matchedFm.volume_oz,
                    percentage_of_liquid: pct
                };
            }
            if (countInCat < list.length) {
                const fm = list[countInCat];
                const budget = latestCoffeeChemistryData.drink_metrics.total_liquid_budget_oz || 1.0;
                const pct = budget > 0 ? ((fm.volume_oz / budget) * 100).toFixed(1) : '0';
                return {
                    name: fm.name,
                    volume_oz: fm.volume_oz,
                    percentage_of_liquid: pct
                };
            }
        }
        return null;
    }

    async function updateCoffeeChemistryWizard() {
        if (currentLabMode !== 'COFFEE' || selectedIngredients.length === 0) {
            latestCoffeeChemistryData = null;
            return;
        }

        let drinkCategory = "Hot Coffee";
        if (coffeeStyle === 'iced') {
            drinkCategory = "Iced Coffee";
        } else if (coffeeStyle === 'espresso_shot') {
            drinkCategory = "Pure Espresso / Short Milk";
        }

        try {
            const r = await fetch('/api/coffee/chemistry/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': window.CSRF_TOKEN },
                body: JSON.stringify({
                    drink_category: drinkCategory,
                    cup_size_oz: coffeeSizeOz,
                    espresso_hot_mode: coffeeEspressoHotMode,
                    americano_style: (coffeeStyle === 'hot' && coffeeBaseType === 'espresso' && coffeeEspressoHotMode === 'water'),
                    ingredients: selectedIngredients.map((ing, idx) => {
                        const ingCopy = { ...ing };
                        if (ingCopy.type === 'COFFEE_BEAN') {
                            ingCopy.coffee_base_type = coffeeBaseType;
                        }
                        let amount = ing.amount;
                        if (ing.isAiBalanced && ing.aiRatio !== undefined && ing.type !== 'COFFEE_BEAN' && ing.type !== 'DAIRY') {
                            amount = Math.round(coffeeAmountForIngredient(ing, idx, coffeeSizeOz, coffeeBaseType) * ing.aiRatio);
                        } else {
                            amount = coffeeAmountForIngredient(ing, idx, coffeeSizeOz, coffeeBaseType);
                        }
                        ingCopy.amount = amount;
                        ingCopy.ingredient_type = ing.type;
                        return ingCopy;
                    })
                })
            });
            const data = await r.json();
            latestCoffeeChemistryData = data;
        } catch (err) {
            console.error("Error updating coffee chemistry wizard:", err);
        }
    }

    async function updateSodaChemistryWizard() {
        if (currentLabMode !== 'SODA' || selectedIngredients.length === 0) {
            latestSodaChemistryData = null;
            return;
        }

        // Ensure a primary anchor is designated if any flavor modifier exists
        const hasPrim = selectedIngredients.some(x => x.isPrimary);
        if (!hasPrim) {
            const firstFlavor = selectedIngredients.find(x => {
                const t = (x.type || x.ingredient_type || '').toUpperCase();
                return ['SODA_SYRUP', 'ADDITIVE', 'OTHER'].includes(t) && !x.isDry;
            });
            if (firstFlavor) {
                firstFlavor.isPrimary = true;
            }
        }

        try {
            const r = await fetch('/api/soda/chemistry/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': window.CSRF_TOKEN },
                body: JSON.stringify({
                    sweetness_style: sodaSweetnessStyle,
                    bottle_scale: bottleScale,
                    ingredients: selectedIngredients.map((ing) => {
                        const ingCopy = { ...ing };
                        ingCopy.ingredient_type = ing.type || ing.ingredient_type;
                        ingCopy.is_primary = ing.isPrimary || false;
                        return ingCopy;
                    })
                })
            });
            const data = await r.json();
            latestSodaChemistryData = data;
        } catch (err) {
            console.error("Error updating soda chemistry wizard:", err);
        }
    }

    async function updateCryoChemistryWizard() {
        if (currentLabMode !== 'SLUSHIE' || selectedIngredients.length === 0) {
            latestCryoChemistryData = null;
            return;
        }

        try {
            const r = await fetch('/api/cryo/chemistry/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': window.CSRF_TOKEN },
                body: JSON.stringify({
                    bottle_scale: bottleScale,
                    ingredients: selectedIngredients.map((ing) => {
                        const ingCopy = { ...ing };
                        ingCopy.ingredient_type = ing.type || ing.ingredient_type;
                        return ingCopy;
                    })
                })
            });
            const data = await r.json();
            latestCryoChemistryData = data;
        } catch (err) {
            console.error("Error updating cryo chemistry wizard:", err);
        }
    }

    function setSodaSweetnessStyle(style) {
        sodaSweetnessStyle = style;
        localStorage.setItem('soda_sweetness_style', style);
        
        ['sweetnessCrisp', 'sweetnessCraft', 'sweetnessFountain'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.classList.toggle('active-lab-mode', (id === 'sweetnessCrisp' && style === 'CRISP') || (id === 'sweetnessCraft' && style === 'CRAFT') || (id === 'sweetnessFountain' && style === 'FOUNTAIN'));
        });
        
        updateSodaChemistryWizard().then(() => {
            updateSelectedArea();
            if (document.getElementById('synthesisReportContainer').style.display !== 'none') {
                triggerFlavorSynthesis();
            }
        });
    } 

    // 🧪 Progress updates queue variables
    let activeProgressTimer = null;
    let activeProgressQueue = [];
    let isProcessingProgressQueue = false;

    async function processActiveProgressQueue() {
        if (isProcessingProgressQueue) return;
        isProcessingProgressQueue = true;
        
        while (activeProgressQueue.length > 0) {
            const nextMsg = activeProgressQueue.shift();
            const textEl = document.getElementById('recommendationProgressText');
            if (textEl) {
                textEl.style.opacity = '0';
                await new Promise(resolve => {
                    activeProgressTimer = setTimeout(resolve, 200);
                });
                textEl.textContent = nextMsg;
                textEl.style.opacity = '1';
                await new Promise(resolve => {
                    activeProgressTimer = setTimeout(resolve, 750);
                });
            } else {
                activeProgressQueue.length = 0; // Clear queue to prevent infinite loop
                break;
            }
        }
        isProcessingProgressQueue = false;
    }

    let allIngredientsHtml = ''; 
    let originalRecipesHtml = '';
    const themeStats = window.THEME_STATS;

    // ☕ Coffee Drink Format State
    let coffeeStyle = 'hot';         // 'hot' | 'iced' | 'espresso_shot'
    let coffeeSizeOz = 12;           // oz: 8, 12, 16, 20, 1, 2
    let coffeeBaseType = 'espresso'; // 'espresso' | 'standard_brew'
    let coffeeBaseAmount = 2;        // shots (1/2/3) for espresso; oz (4/8/12/16) for standard_brew
    let coffeeEspressoHotMode = localStorage.getItem('coffee_espresso_hot_mode') || 'shots';
    let isMixSealed = false;

    function setEspressoHotMode(mode) {
        coffeeEspressoHotMode = mode;
        localStorage.setItem('coffee_espresso_hot_mode', mode);
        const waterBtn = document.getElementById('hotModeWater');
        const shotsBtn = document.getElementById('hotModeShots');
        if (waterBtn) waterBtn.classList.toggle('active-lab-mode', mode === 'water');
        if (shotsBtn) shotsBtn.classList.toggle('active-lab-mode', mode === 'shots');
        
        recalculateCoffeeBaseAmount();
        updateCoffeeChemistryWizard().then(() => {
            updateSelectedArea();
            if (document.getElementById('synthesisReportContainer').style.display !== 'none') {
                triggerFlavorSynthesis();
            }
        });
    }

    function getBaselineAmount(ing, index) {
        if (currentLabMode === 'COFFEE') {
            return coffeeAmountForIngredient(ing, index, coffeeSizeOz, coffeeBaseType);
        } else {
            const isDry = ing.isDry === true || ing.isDry === 'true';
            if (isDry) {
                return 15.0;
            } else {
                const baseVolume = index === 0 ? 80.0 : (index === 1 ? 40.0 : 20.0);
                return baseVolume;
            }
        }
    }


    function setBottleScale(scale) {
        bottleScale = parseFloat(scale);
        
        // Toggle active classes for Soda
        const sodaBtns = {
            1.0: 'scale1L',
            0.5: 'scale05L',
            0.355: 'scale12oz'
        };
        Object.entries(sodaBtns).forEach(([val, id]) => {
            const el = document.getElementById(id);
            if (el) el.classList.toggle('active-lab-mode', Math.abs(bottleScale - parseFloat(val)) < 0.01);
        });

        // Toggle active classes for Cryo
        const cryoBtns = {
            0.5: 'scale16oz',
            1.0: 'scale32oz',
            1.5: 'scale48oz',
            2.0: 'scale64oz'
        };
        Object.entries(cryoBtns).forEach(([val, id]) => {
            const el = document.getElementById(id);
            if (el) el.classList.toggle('active-lab-mode', Math.abs(bottleScale - parseFloat(val)) < 0.01);
        });

        if (currentLabMode === 'SODA') {
            updateSodaChemistryWizard().then(() => {
                updateSelectedArea();
                if (document.getElementById('synthesisReportContainer').style.display !== 'none') {
                    triggerFlavorSynthesis();
                }
            });
        } else if (currentLabMode === 'SLUSHIE') {
            updateCryoChemistryWizard().then(() => {
                updateSelectedArea();
                if (document.getElementById('synthesisReportContainer').style.display !== 'none') {
                    triggerFlavorSynthesis();
                }
            });
        } else {
            updateSelectedArea();
        }
    }

    // ☕ Coffee drink format controls
    function getTotalCoffeeBeansGrams() {
        if (coffeeBaseType === 'espresso') {
            return 18.0 * coffeeBaseAmount;
        } else {
            return Math.round((7.0 / 6.0) * coffeeBaseAmount);
        }
    }

    function adjustCoffeeBeanSplitButtons(id, change) {
        const isEspresso = (coffeeBaseType === 'espresso');
        const coffeeBeans = selectedIngredients.filter(x => (x.type || x.ingredient_type || '').toUpperCase() === 'COFFEE_BEAN');
        if (coffeeBeans.length < 2) return;
        
        // Find target bean
        const targetBean = coffeeBeans.find(x => x.id == id);
        if (!targetBean) return;
        
        if (isEspresso) {
            // Espresso: change is in shots (-1 or 1)
            const currentShots = Math.round(parseFloat(targetBean.amount || 0) / 18.0);
            const totalShots = coffeeBaseAmount;
            const newShots = currentShots + change;
            
            // Clamp target bean shots
            if (newShots < 0 || newShots > totalShots) return;
            
            // Find other beans
            const otherBeans = coffeeBeans.filter(x => x.id != id);
            
            // Calculate how much we need to subtract/add from other beans
            let remainingChange = Math.abs(change);
            
            if (change > 0) {
                // We are increasing target bean. We need to decrease other beans.
                for (let i = 0; i < otherBeans.length; i++) {
                    const otherShots = Math.round(parseFloat(otherBeans[i].amount || 0) / 18.0);
                    if (otherShots > 0) {
                        const reduceBy = Math.min(otherShots, remainingChange);
                        otherBeans[i].amount = (otherShots - reduceBy) * 18.0;
                        otherBeans[i].isUserOverridden = true;
                        remainingChange -= reduceBy;
                        if (remainingChange === 0) break;
                    }
                }
            } else {
                // We are decreasing target bean. We need to increase other beans.
                // We add it to the first other bean.
                const firstOtherShots = Math.round(parseFloat(otherBeans[0].amount || 0) / 18.0);
                otherBeans[0].amount = (firstOtherShots + Math.abs(change)) * 18.0;
                otherBeans[0].isUserOverridden = true;
                remainingChange = 0;
            }
            
            if (remainingChange === 0) {
                targetBean.amount = newShots * 18.0;
                targetBean.isUserOverridden = true;
            }
        } else {
            // Standard Brew: change is in grams
            const totalGrams = getTotalCoffeeBeansGrams();
            const currentGrams = parseFloat(targetBean.amount || 0);
            const newGrams = currentGrams + change;
            
            if (newGrams < 0 || newGrams > totalGrams) return;
            
            const otherBeans = coffeeBeans.filter(x => x.id != id);
            let remainingChange = Math.abs(change);
            
            if (change > 0) {
                // Decrease other beans
                for (let i = 0; i < otherBeans.length; i++) {
                    const otherG = parseFloat(otherBeans[i].amount || 0);
                    if (otherG > 0) {
                        const reduceBy = Math.min(otherG, remainingChange);
                        otherBeans[i].amount = otherG - reduceBy;
                        otherBeans[i].isUserOverridden = true;
                        remainingChange -= reduceBy;
                        if (remainingChange === 0) break;
                    }
                }
            } else {
                // Increase other beans (add it to the first other bean)
                otherBeans[0].amount = parseFloat(otherBeans[0].amount || 0) + Math.abs(change);
                otherBeans[0].isUserOverridden = true;
                remainingChange = 0;
            }
            
            if (remainingChange === 0) {
                targetBean.amount = newGrams;
                targetBean.isUserOverridden = true;
            }
        }
        
        // Trigger updates asynchronously
        updateCoffeeChemistryWizard().then(() => {
            updateSelectedArea();
            if (document.getElementById('synthesisReportContainer').style.display !== 'none') {
                triggerFlavorSynthesis();
            }
        });
    }

    function removeCoffeeBeanSplit(id) {
        // Find target index in selectedIngredients
        const index = selectedIngredients.findIndex(x => x.id == id && (x.type || x.ingredient_type || '').toUpperCase() === 'COFFEE_BEAN');
        if (index === -1) return;
        
        // Remove the bean
        selectedIngredients.splice(index, 1);
        
        // Restore remaining coffee beans to the full budget
        const remainingBeans = selectedIngredients.filter(x => (x.type || x.ingredient_type || '').toUpperCase() === 'COFFEE_BEAN');
        if (remainingBeans.length === 1) {
            remainingBeans[0].amount = getTotalCoffeeBeansGrams();
            remainingBeans[0].isUserOverridden = false;
        } else if (remainingBeans.length > 1) {
            const totalGrams = getTotalCoffeeBeansGrams();
            remainingBeans.forEach(x => {
                x.amount = totalGrams / remainingBeans.length;
                x.isUserOverridden = true;
            });
        }
        
        // Trigger updates asynchronously
        updateCoffeeChemistryWizard().then(() => {
            updateSelectedArea();
            if (document.getElementById('synthesisReportContainer').style.display !== 'none') {
                triggerFlavorSynthesis();
            }
        });
    }

    function recalculateCoffeeBaseAmount() {
        const oldBudget = getTotalCoffeeBeansGrams();

        if (coffeeBaseType === 'espresso') {
            if (coffeeStyle === 'espresso_shot') {
                if (coffeeSizeOz === 1) {
                    coffeeBaseAmount = 1;
                } else if (coffeeSizeOz === 2) {
                    coffeeBaseAmount = 2;
                } else if (coffeeSizeOz === 3) {
                    coffeeBaseAmount = 3;
                } else if (coffeeSizeOz === 4) {
                    coffeeBaseAmount = 4;
                } else {
                    coffeeBaseAmount = 2;
                }
            } else { // hot or iced
                if (coffeeSizeOz === 8) {
                    coffeeBaseAmount = 1;
                } else if (coffeeSizeOz === 12) {
                    coffeeBaseAmount = 2;
                } else if (coffeeSizeOz === 16) {
                    coffeeBaseAmount = 3;
                } else if (coffeeSizeOz === 20) {
                    coffeeBaseAmount = 4;
                } else {
                    coffeeBaseAmount = 2;
                }
            }
        } else { // standard_brew
            if (coffeeStyle === 'espresso_shot') {
                coffeeBaseAmount = 2;
            } else if (coffeeStyle === 'iced') {
                coffeeBaseAmount = coffeeSizeOz * 0.60 * 0.70;
            } else { // hot
                coffeeBaseAmount = coffeeSizeOz * 0.70;
            }
        }

        const newBudget = getTotalCoffeeBeansGrams();
        if (oldBudget > 0 && Math.abs(oldBudget - newBudget) > 0.001) {
            const coffeeBeans = selectedIngredients.filter(x => (x.type || x.ingredient_type || '').toUpperCase() === 'COFFEE_BEAN');
            if (coffeeBeans.length > 0) {
                const isEspresso = (coffeeBaseType === 'espresso');
                const targetShotsCount = isEspresso ? Math.round(newBudget / 18.0) : 999;
                
                if (isEspresso && targetShotsCount < 2 && coffeeBeans.length > 1) {
                    // Merge splits back into the first bean
                    const firstBean = coffeeBeans[0];
                    firstBean.amount = newBudget;
                    firstBean.isUserOverridden = false;
                    selectedIngredients = selectedIngredients.filter(x => 
                        (x.type || x.ingredient_type || '').toUpperCase() !== 'COFFEE_BEAN' || x.id === firstBean.id
                    );
                } else if (coffeeBeans.length === 1) {
                    coffeeBeans[0].amount = newBudget;
                } else if (isEspresso) {
                    let sumOfShots = 0;
                    const shotsList = coffeeBeans.map(x => {
                        const s = Math.round((parseFloat(x.amount || 0) / oldBudget) * targetShotsCount);
                        sumOfShots += s;
                        return s;
                    });
                    
                    let diff = targetShotsCount - sumOfShots;
                    if (diff !== 0) {
                        shotsList[0] = Math.max(0, shotsList[0] + diff);
                    }
                    
                    coffeeBeans.forEach((x, i) => {
                        x.amount = shotsList[i] * 18.0;
                    });
                } else {
                    const totalCurrentGrams = coffeeBeans.reduce((sum, x) => sum + parseFloat(x.amount || 0), 0);
                    if (totalCurrentGrams > 0) {
                        coffeeBeans.forEach(x => {
                            x.amount = newBudget * (parseFloat(x.amount) / totalCurrentGrams);
                        });
                    } else {
                        coffeeBeans.forEach(x => {
                            x.amount = newBudget / coffeeBeans.length;
                        });
                    }
                }
            }
        }
    }

    function setCoffeeStyle(style) {
        coffeeStyle = style;
        localStorage.setItem('coffee_style', style);
        // Update style button states
        ['styleHot', 'styleIced', 'styleShot'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.classList.remove('active-lab-mode');
        });
        const styleMap = { hot: 'styleHot', iced: 'styleIced', espresso_shot: 'styleShot' };
        const activeBtn = document.getElementById(styleMap[style]);
        if (activeBtn) activeBtn.classList.add('active-lab-mode');

        // Re-render size options based on style
        const shotMode = (style === 'espresso_shot');
        const sizeBtns = document.getElementById('coffeeSizeBtns');
        if (shotMode) {
            sizeBtns.innerHTML = `
                <button type="button" class="btn btn-md btn-glass-toggle py-2 fs-6" id="size1oz" onclick="setCoffeeSize(1)">Single (1oz)</button>
                <button type="button" class="btn btn-md btn-glass-toggle py-2 fs-6" id="size2oz" onclick="setCoffeeSize(2)">Double (2oz)</button>
                <button type="button" class="btn btn-md btn-glass-toggle py-2 fs-6" id="size3oz" onclick="setCoffeeSize(3)">Triple (3oz)</button>
                <button type="button" class="btn btn-md btn-glass-toggle py-2 fs-6" id="size4oz" onclick="setCoffeeSize(4)">Quad (4oz)</button>
            `;
            // Force coffee base type to espresso for shots
            coffeeBaseType = 'espresso';
            localStorage.setItem('coffee_base_type', 'espresso');
            document.getElementById('baseEspresso').classList.add('active-lab-mode');
            document.getElementById('baseStandardBrew').classList.remove('active-lab-mode');
            const coffeeBaseTypeField = document.getElementById('coffeeBaseTypeField');
            if (coffeeBaseTypeField) coffeeBaseTypeField.value = 'espresso';

            const prev = coffeeSizeOz;
            const defaultSize = [1,2,3,4].includes(prev) ? prev : 2;
            setCoffeeSize(defaultSize);
        } else {
            // Default 12oz selected
            const prev = coffeeSizeOz;
            const defaultSize = [8,12,16,20].includes(prev) ? prev : 12;
            sizeBtns.innerHTML = `
                <button type="button" class="btn btn-md btn-glass-toggle py-2 fs-6" id="size8oz"  onclick="setCoffeeSize(8)">8oz</button>
                <button type="button" class="btn btn-md btn-glass-toggle py-2 fs-6" id="size12oz" onclick="setCoffeeSize(12)">12oz</button>
                <button type="button" class="btn btn-md btn-glass-toggle py-2 fs-6" id="size16oz" onclick="setCoffeeSize(16)">16oz</button>
                <button type="button" class="btn btn-md btn-glass-toggle py-2 fs-6" id="size20oz" onclick="setCoffeeSize(20)">20oz</button>
            `;
            setCoffeeSize(defaultSize);
        }

        // Show/hide Coffee Base Type selector based on style (shots are always espresso)
        const baseLabel = document.getElementById('coffeeBaseLabel');
        const baseBtns = document.getElementById('coffeeBaseBtns');
        if (baseLabel) baseLabel.style.display = shotMode ? 'none' : '';
        if (baseBtns) baseBtns.style.display = shotMode ? 'none' : '';

        // Update hidden field and refresh compound display
        const coffeeStyleField = document.getElementById('coffeeStyleField');
        if (coffeeStyleField) coffeeStyleField.value = style;
        
        recalculateCoffeeBaseAmount();
        updateEspressoHotModeContainer();
        updateCoffeeChemistryWizard().then(() => {
            updateSelectedArea();
            if (document.getElementById('synthesisReportContainer').style.display !== 'none') {
                triggerFlavorSynthesis();
            }
        });
    }

    function updateEspressoHotModeContainer() {
        const showHotEspressoAdj = (currentLabMode === 'COFFEE' && coffeeStyle === 'hot' && coffeeBaseType === 'espresso');
        const adjContainer = document.getElementById('espressoHotModeContainer');
        if (adjContainer) adjContainer.style.display = showHotEspressoAdj ? 'block' : 'none';
        
        // Sync active class on hot/water buttons
        const waterBtn = document.getElementById('hotModeWater');
        const shotsBtn = document.getElementById('hotModeShots');
        if (waterBtn) waterBtn.classList.toggle('active-lab-mode', coffeeEspressoHotMode === 'water');
        if (shotsBtn) shotsBtn.classList.toggle('active-lab-mode', coffeeEspressoHotMode === 'shots');
    }

    function setCoffeeSize(oz) {
        coffeeSizeOz = parseFloat(oz);
        localStorage.setItem('coffee_size_oz', coffeeSizeOz);
        // Mark the active button
        document.querySelectorAll('#coffeeSizeBtns button').forEach(btn => {
            btn.classList.remove('active-lab-mode');
        });
        // Find the button with matching onclick value
        document.querySelectorAll('#coffeeSizeBtns button').forEach(btn => {
            const match = btn.getAttribute('onclick');
            if (match && match.includes('(' + oz + ')')) {
                btn.classList.add('active-lab-mode');
            }
        });
        const drinkSizeOzField = document.getElementById('drinkSizeOzField');
        if (drinkSizeOzField) drinkSizeOzField.value = coffeeSizeOz;
        
        recalculateCoffeeBaseAmount();
        updateEspressoHotModeContainer();
        updateCoffeeChemistryWizard().then(() => {
            updateSelectedArea();
            if (document.getElementById('synthesisReportContainer').style.display !== 'none') {
                triggerFlavorSynthesis();
            }
        });
    }

    function setCoffeeBaseType(type) {
        coffeeBaseType = type;
        localStorage.setItem('coffee_base_type', type);
        document.getElementById('baseEspresso').classList.toggle('active-lab-mode', type === 'espresso');
        document.getElementById('baseStandardBrew').classList.toggle('active-lab-mode', type === 'standard_brew');
        const coffeeBaseTypeField = document.getElementById('coffeeBaseTypeField');
        if (coffeeBaseTypeField) coffeeBaseTypeField.value = type;

        recalculateCoffeeBaseAmount();
        updateEspressoHotModeContainer();
        updateCoffeeChemistryWizard().then(() => {
            updateSelectedArea();
            if (document.getElementById('synthesisReportContainer').style.display !== 'none') {
                triggerFlavorSynthesis();
            }
        });
    }

    function getIceAmountOz(sizeOz) {
        return sizeOz * 0.40;
    }

    /**
     * Calculate the amount for a coffee ingredient based on current drink settings.
     * Uses global coffeeBaseAmount (shots for espresso, oz for standard brew).
     * @param {object} ing - Ingredient object
     * @param {number} index - Position in the ingredient list (0 = bean/base)
     * @param {number} sizeOz - Target drink size in oz
     * @param {string} baseType - 'espresso' | 'standard_brew'
     * @returns {number} amount in appropriate units (g for beans, ml for liquids)
     */
    function coffeeAmountForIngredient(ing, index, sizeOz, baseType) {
        const isDryCoffee = (ing.type === 'COFFEE_BEAN');
        const isShot = (coffeeStyle === 'espresso_shot');

        if (isDryCoffee) {
            const selectedBean = selectedIngredients.find(x => x.id == ing.id && (x.type || x.ingredient_type || '').toUpperCase() === 'COFFEE_BEAN');
            if (selectedBean && selectedBean.amount !== null && selectedBean.amount !== undefined) {
                const coffeeBeans = selectedIngredients.filter(x => (x.type || x.ingredient_type || '').toUpperCase() === 'COFFEE_BEAN');
                if (coffeeBeans.length > 1) {
                    return selectedBean.amount;
                }
            }
            if (baseType === 'espresso') {
                // coffeeBaseAmount = number of shots; each shot ~18g
                return 18.0 * coffeeBaseAmount;
            } else {
                // coffeeBaseAmount = oz of standard brew; typical ratio: ~7g per 6oz cup
                return Math.round((7.0 / 6.0) * coffeeBaseAmount);
            }
        }

        if (isShot) {
            // For pure espresso shots, keep dairy and additives minimal
            return (ing.isReadyToDrink || ing.type === 'DAIRY' || ing.type === 'ADDITIVE') ? 10.0 : 8.0;
        }

        // Determine if this ingredient is the primary ready-to-drink base (the volume filler)
        let isVolumeFiller = false;
        const isRtd = ing.isReadyToDrink || (ing.profile && (ing.profile.is_ready_to_drink === true || ing.profile.is_ready_to_drink === 'true'));
        if (isRtd) {
            let firstRtdIdx = -1;
            for (let i = 0; i < selectedIngredients.length; i++) {
                const sIng = selectedIngredients[i];
                if (sIng.isReadyToDrink || (sIng.profile && (sIng.profile.is_ready_to_drink === true || sIng.profile.is_ready_to_drink === 'true'))) {
                    firstRtdIdx = i;
                    break;
                }
            }
            if (firstRtdIdx === -1) {
                isVolumeFiller = true;
            } else {
                isVolumeFiller = (index === firstRtdIdx);
            }
        } else if (ing.type === 'DAIRY') {
            let hasAnyRtd = selectedIngredients.some(sIng => sIng.isReadyToDrink);
            if (!hasAnyRtd) {
                const firstDairyIdx = selectedIngredients.findIndex(sIng => sIng.type === 'DAIRY');
                isVolumeFiller = (firstDairyIdx === -1 || index === firstDairyIdx);
            }
        }

        // Scale ready-to-drink volume filler to fill remaining volume for espresso bases
        if (baseType === 'espresso' && isVolumeFiller) {
            const liquidBudget = (coffeeStyle === 'iced') ? sizeOz * 0.6 : sizeOz;
            const espressoVol = coffeeBaseAmount * 0.9;
            const hotWaterVol = (coffeeEspressoHotMode === 'water') ? espressoVol : 0.0;
            
            let modifierVolOz = 0;
            let numModifiers = 0;
            let combinedSwe = 0;
            selectedIngredients.forEach((otherIng) => {
                const otherType = (otherIng.type || otherIng.ingredient_type || '').toUpperCase();
                if (otherType !== 'COFFEE_BEAN' && otherType !== 'DAIRY' && !otherIng.isReadyToDrink) {
                    numModifiers++;
                    combinedSwe += parseFloat(otherIng.sweetness || 3.0);
                    const scale = (sizeOz / 12.0) * (coffeeStyle === 'iced' ? 0.6 : 1.0);
                    const volMl = 30.0 * scale;
                    modifierVolOz += volMl / 29.5735;
                }
            });
            
            let capPct = (numModifiers > 1 || combinedSwe > 5) ? 0.10 : 0.15;
            if (coffeeStyle === 'iced') {
                capPct += 0.02;
            }
            const maxModifiersOz = liquidBudget * capPct;
            if (modifierVolOz > maxModifiersOz) {
                modifierVolOz = maxModifiersOz;
            }
            
            let dairyVol = liquidBudget - espressoVol - modifierVolOz - hotWaterVol;
            if (dairyVol < 0.0) dairyVol = 0.0;
            if (coffeeStyle === 'iced') {
                dairyVol = dairyVol * 0.9;
            }
            const targetAdditiveMl = dairyVol * 29.5735;
            return Math.max(30.0, Math.round(targetAdditiveMl));
        }

        // For standard brew or non-volume-filler ingredients (syrups/accents/minor additives):
        // Scale syrups/additives proportionally to drink size
        let scaleFactor = sizeOz / 12.0;
        
        // Ice displacement factor: if iced, reduce liquid volumes by 40% (multiply by 0.6)
        if (coffeeStyle === 'iced') {
            scaleFactor *= 0.6;
        }

        if (ing.isReadyToDrink || ing.type === 'DAIRY') {
            return Math.round(60.0 * scaleFactor);
        }
        return Math.round(30.0 * scaleFactor);
    }


    function formatImperialVolume(ml) {
        const oz = ml * 0.033814;
        if (oz >= 1.0) return oz.toFixed(1) + 'oz';
        
        // 1 Tbsp = 14.7868ml, 1 tsp = 4.92892ml
        if (ml >= 2.5) {
            let tbsp = Math.floor(ml / 14.7868);
            let remMl = ml - tbsp * 14.7868;
            let tsp = Math.round(remMl / 4.92892);
            
            if (tsp >= 3) {
                tbsp += 1;
                tsp -= 3;
            }
            
            if (tbsp > 0 && tsp > 0) {
                return `${tbsp} Tbsp + ${tsp} tsp`;
            } else if (tbsp > 0) {
                return `${tbsp} Tbsp`;
            } else if (tsp > 0) {
                return `${tsp} tsp`;
            }
        }
        
        return oz.toFixed(2) + 'oz';
    }

    console.log("🔬 LABORATORY SUBSTRATE LOADED");
    
// ==========================================
// 5. EVENT LISTENERS & INITIALIZATION
// ==========================================
document.addEventListener('DOMContentLoaded', function() {
        allIngredientsHtml = document.getElementById('availableIngredients').innerHTML;
        const simRes = document.getElementById('similarRecipes');
        if (simRes) {
            originalRecipesHtml = simRes.innerHTML;
        }
        
        // Initialize from localStorage
        const savedMode = localStorage.getItem('lab_mode') || 'SODA';
        const savedRecMode = localStorage.getItem('recommendation_mode') || 'standard';
        const savedEngineMode = localStorage.getItem('engine_mode') || 'algorithmic';
        const savedCoffeeStyle = localStorage.getItem('coffee_style') || 'hot';
        const savedCoffeeSizeOz = parseFloat(localStorage.getItem('coffee_size_oz') || '12');
        const savedCoffeeBaseType = localStorage.getItem('coffee_base_type') || 'espresso';
        const savedCoffeeBaseAmount = savedCoffeeBaseType === 'espresso'
            ? parseInt(localStorage.getItem('coffee_base_shots') || '2')
            : parseInt(localStorage.getItem('coffee_base_brew_oz') || '8');

        setLabMode(savedMode, true); 
        setRecommendationMode(savedRecMode);
        setEngineMode(savedEngineMode);

        // Apply saved coffee controls (run after setLabMode so DOM is ready)
        coffeeStyle = savedCoffeeStyle;
        coffeeSizeOz = savedCoffeeSizeOz;
        coffeeBaseType = savedCoffeeBaseType;
        
        // Sync hidden fields
        const cStyleField = document.getElementById('coffeeStyleField');
        const cBaseField = document.getElementById('coffeeBaseTypeField');
        const cSizeField = document.getElementById('drinkSizeOzField');
        if (cStyleField) cStyleField.value = savedCoffeeStyle;
        if (cBaseField) cBaseField.value = savedCoffeeBaseType;
        if (cSizeField) cSizeField.value = savedCoffeeSizeOz;
        
        // Apply saved selections via setters
        setCoffeeStyle(savedCoffeeStyle);
        if (savedCoffeeStyle === 'espresso_shot') {
            const validSize = [1, 2, 3, 4].includes(savedCoffeeSizeOz) ? savedCoffeeSizeOz : 2;
            setCoffeeSize(validSize);
        } else {
            const validSize = [8, 12, 16, 20].includes(savedCoffeeSizeOz) ? savedCoffeeSizeOz : 12;
            setCoffeeSize(validSize);
        }
        setCoffeeBaseType(savedCoffeeBaseType);
    });

    function setRecommendationMode(mode) {
        recommendationMode = mode;
        localStorage.setItem('recommendation_mode', mode);
        
        const stdBtn = document.getElementById('toggleStandard');
        const expBtn = document.getElementById('toggleExperimental');
        
        if (mode === 'experimental') {
            stdBtn.classList.remove('active-lab-mode');
            stdBtn.classList.add('text-dim');
            expBtn.classList.add('active-lab-mode');
            expBtn.classList.remove('text-dim');
        } else {
            expBtn.classList.remove('active-lab-mode');
            expBtn.classList.add('text-dim');
            stdBtn.classList.add('active-lab-mode');
            stdBtn.classList.remove('text-dim');
        }
        
        setLabMode(currentLabMode); // Refresh filtering
        
        if (selectedIngredients.length > 0) {
            fetchRecommendations();
        }
    }

    let engineMode = 'algorithmic';
    function setEngineMode(mode) {
        engineMode = mode;
        localStorage.setItem('engine_mode', mode);
        
        const algoBtn = document.getElementById('toggleEngineAlgorithmic');
        const aiBtn = document.getElementById('toggleEngineAI');
        
        if (algoBtn) {
            algoBtn.classList.toggle('active-lab-mode', mode === 'algorithmic');
            algoBtn.classList.toggle('text-dim', mode !== 'algorithmic');
        }
        
        if (aiBtn) {
            aiBtn.classList.toggle('active-lab-mode', mode === 'ai');
            aiBtn.classList.toggle('text-dim', mode !== 'ai');
        }
        
        if (selectedIngredients.length > 0) {
            fetchRecommendations();
        }
    }

    function setLabMode(mode, isInit = false) {
        cancelInFlightLLMCalls();
        mode = mode.toUpperCase();
        currentLabMode = mode;
        selectedIngredients = [];
        
        // Save to storage
        localStorage.setItem('lab_mode', mode);
        
        // Toggle Global Theme Class
        document.documentElement.classList.remove('theme-coffee', 'theme-slushie');
        if (mode === 'COFFEE') {
            document.documentElement.classList.add('theme-coffee');
        } else if (mode === 'SLUSHIE') {
            document.documentElement.classList.add('theme-slushie');
        }

        // Update Buttons
        document.getElementById('modeSoda').classList.toggle('active', mode === 'SODA');
        document.getElementById('modeCoffee').classList.toggle('active', mode === 'COFFEE');
        document.getElementById('modeSlushie').classList.toggle('active', mode === 'SLUSHIE');
        
        // Update Filtered Ingredients
        const cards = document.querySelectorAll('#availableIngredients .ingredient-card');
        cards.forEach(card => {
            const type = card.getAttribute('data-type');
            const systems = card.getAttribute('data-systems') || "SODA,COFFEE,SLUSHIE";
            const systemList = systems.split(',');
            
            let isTypeMatch = false;
            if (mode === 'SODA') {
                isTypeMatch = (type === 'SODA_SYRUP' || type === 'OTHER');
            } else if (mode === 'COFFEE') {
                isTypeMatch = (type === 'COFFEE_BEAN');
            } else if (mode === 'SLUSHIE') {
                isTypeMatch = (type === 'SODA_SYRUP' || type === 'OTHER');
            }
            
            const isSystemMatch = systemList.map(s => s.trim()).includes(mode);
            const isExperimental = (recommendationMode === 'experimental');
            
            // In experimental mode, any ingredient should be considered for inclusion.
            if (isExperimental) {
                card.style.display = 'block';
            } else {
                card.style.display = (isTypeMatch && isSystemMatch) ? 'block' : 'none';
            }
        });
        
        // Update UI Text removed for cleaner mixture-focused interface
        document.getElementById('drinkTypeField').value = mode;
        
        // Hall of Fame stats removed in favor of AI Assistant
        
        // Filter Recent Recipes to 5 matching the theme
        const recentCards = document.querySelectorAll('.recent-recipe-card');
        let visibleCount = 0;
        recentCards.forEach(card => {
            if (card.getAttribute('data-drink-type') === mode && visibleCount < 5) {
                card.style.display = 'block';
                visibleCount++;
            } else {
                card.style.display = 'none';
            }
        });
        
        const noRecordsMsg = document.getElementById('noRecentRecipesMsg');
        if (noRecordsMsg) {
            noRecordsMsg.style.display = visibleCount === 0 ? 'block' : 'none';
        }
        
        resetMixer();
    }

    function getBadgeColor(category) {
        if (!category) return 'bg-neutral';
        return `bg-${category.toLowerCase().trim()}`;
    }

    // Global state for AI synthesis history
    let aiChatHistory = [];

    // AbortControllers and Debouncing for LLM calls
    let recommendationsController = null;
    let synthesisController = null;
    let surpriseController = null;

    let fetchRecommendationsTimeout = null;
    let triggerFlavorSynthesisTimeout = null;

    
// ==========================================
// 4. AI & API SERVICES
// ==========================================
function cancelInFlightLLMCalls() {
        if (recommendationsController) {
            recommendationsController.abort();
            recommendationsController = null;
        }
        if (synthesisController) {
            synthesisController.abort();
            synthesisController = null;
        }
        if (surpriseController) {
            surpriseController.abort();
            surpriseController = null;
        }
        
        // Also clear any pending debounce timeouts
        if (fetchRecommendationsTimeout) {
            clearTimeout(fetchRecommendationsTimeout);
            fetchRecommendationsTimeout = null;
        }
        if (triggerFlavorSynthesisTimeout) {
            clearTimeout(triggerFlavorSynthesisTimeout);
            triggerFlavorSynthesisTimeout = null;
        }
    }

    function debouncedFetchRecommendations() {
        if (fetchRecommendationsTimeout) {
            clearTimeout(fetchRecommendationsTimeout);
        }
        // Cancel currently in-flight suggestion calls immediately for instant responsiveness
        if (recommendationsController) {
            recommendationsController.abort();
            recommendationsController = null;
        }
        
        fetchRecommendationsTimeout = setTimeout(() => {
            fetchRecommendations();
        }, 500);
    }

    function debouncedTriggerFlavorSynthesis() {
        if (triggerFlavorSynthesisTimeout) {
            clearTimeout(triggerFlavorSynthesisTimeout);
        }
        // Cancel currently in-flight synthesis calls immediately
        if (synthesisController) {
            synthesisController.abort();
            synthesisController = null;
        }
        
        triggerFlavorSynthesisTimeout = setTimeout(() => {
            triggerFlavorSynthesis();
        }, 500);
    }

    // Stub for removed assistant window
    function appendChatMessage(role, content) {
        console.log(`[Lab Assistant] ${role}: ${content}`);
    }

    // Stub for proactive suggestions
    function triggerProactiveSuggestion() {
        // No-op in single-window mode
    }

    function selectIngredient(id, name, intensity, category, profile = null, silent = false, amount = null, sweetness = 0, acidity = 0, bitterness = 0, complexity = 0, type = null, isReadyToDrink = false, isDry = false, roastLevel = null, flavorNotes = '', isDecaf = false) {
        console.log("Integrating reagent:", name);
        
        if (isMixSealed) {
            console.log("Mix is sealed. Blocking ingredient addition.");
            return;
        }

        const existing = selectedIngredients.find(ing => ing.id == id);
        if (existing) {
            const idx = selectedIngredients.indexOf(existing);
            const standard = getBaselineAmount(existing, idx);
            const currentAmt = existing.amount !== null ? existing.amount : standard;
            
            const parsedAmount = amount ? parseFloat(amount) : null;
            let addedAmt = parsedAmount !== null ? parsedAmount : standard;
            
            existing.amount = currentAmt + addedAmt;
            existing.isUserOverridden = true;
            existing.isAiBalanced = true;
            existing.aiRatio = standard > 0 ? (existing.amount / standard) : 1.0;
            console.log(`Re-added existing reagent: ${existing.name}. Updated amount to ${existing.amount} (aiRatio: ${existing.aiRatio})`);
            
            if (currentLabMode === 'COFFEE' && !silent) {
                updateCoffeeChemistryWizard().then(() => {
                    updateSelectedArea();
                    if (document.getElementById('synthesisReportContainer').style.display !== 'none') {
                        debouncedTriggerFlavorSynthesis();
                    }
                    debouncedFetchRecommendations();
                });
            } else if (currentLabMode === 'SODA' && !silent) {
                updateSodaChemistryWizard().then(() => {
                    updateSelectedArea();
                    if (document.getElementById('synthesisReportContainer').style.display !== 'none') {
                        debouncedTriggerFlavorSynthesis();
                    }
                    debouncedFetchRecommendations();
                });
            } else if (currentLabMode === 'SLUSHIE' && !silent) {
                updateCryoChemistryWizard().then(() => {
                    updateSelectedArea();
                    if (document.getElementById('synthesisReportContainer').style.display !== 'none') {
                        debouncedTriggerFlavorSynthesis();
                    }
                    debouncedFetchRecommendations();
                });
            } else {
                updateSelectedArea();
                if (!silent) {
                    debouncedFetchRecommendations();
                }
            }
            return;
        }

        const profileObj = typeof profile === 'string' && profile.trim() !== '' ? JSON.parse(profile) : profile;
        const parsedAmount = amount ? parseFloat(amount) : null;
        const isAiBalanced = (engineMode === 'ai' && parsedAmount !== null);
        let aiRatio = 1.0;
        
        if (isAiBalanced && currentLabMode === 'COFFEE') {
            const tempIng = { type: type };
            const idxForStandard = selectedIngredients.length;
            const standard = coffeeAmountForIngredient(tempIng, idxForStandard, coffeeSizeOz, coffeeBaseType);
            aiRatio = standard > 0 ? (parsedAmount / standard) : 1.0;
        }

        let parsedNotes = [];
        if (flavorNotes) {
            parsedNotes = flavorNotes.split(',').map(s => s.trim().toLowerCase()).filter(s => s.length > 0);
        } else if (profileObj && profileObj.flavor_notes) {
            if (Array.isArray(profileObj.flavor_notes)) {
                parsedNotes = profileObj.flavor_notes;
            } else {
                parsedNotes = profileObj.flavor_notes.split(',').map(s => s.trim().toLowerCase()).filter(s => s.length > 0);
            }
        }

        selectedIngredients.push({
            id: id,
            name: name,
            intensity: profileObj ? profileObj.intensity : parseInt(intensity), 
            sweetness: profileObj ? profileObj.sweetness : parseInt(sweetness),
            acidity: profileObj ? profileObj.acidity : parseInt(acidity),
            bitterness: profileObj ? profileObj.bitterness : parseInt(bitterness),
            complexity: profileObj ? profileObj.complexity : parseInt(complexity),
            category: category,
            type: type,
            amount: parsedAmount,
            isAiBalanced: isAiBalanced,
            aiRatio: aiRatio,
            isReadyToDrink: isReadyToDrink || (profileObj && (profileObj.is_ready_to_drink === true || profileObj.is_ready_to_drink === 'true')),
            isDry: isDry || (profileObj && (profileObj.is_dry === true || profileObj.is_dry === 'true')),
            roast_level: roastLevel || (profileObj ? profileObj.roast_level : null),
            body_intensity: profileObj ? profileObj.intensity : parseInt(intensity),
            acidity_score: profileObj ? profileObj.acidity : parseInt(acidity),
            bitterness_score: profileObj ? profileObj.bitterness : parseInt(bitterness),
            flavor_notes: parsedNotes,
            is_decaf: isDecaf || (profileObj ? (profileObj.is_decaf === true || profileObj.is_decaf === 'true') : false) || name.toLowerCase().includes('decaf'),
            profile: profileObj,
            isPrimary: false
        });

        // Split grams budget equally among all coffee beans in the mix only if the new ingredient is a coffee bean
        const isNewIngredientCoffeeBean = (type || '').toUpperCase() === 'COFFEE_BEAN';
        const coffeeBeans = selectedIngredients.filter(x => (x.type || x.ingredient_type || '').toUpperCase() === 'COFFEE_BEAN');
        if (isNewIngredientCoffeeBean && coffeeBeans.length > 0) {
            const totalGrams = getTotalCoffeeBeansGrams();
            const isEspresso = (coffeeBaseType === 'espresso');
            const count = coffeeBeans.length;
            
            if (isEspresso) {
                const totalShots = coffeeBaseAmount;
                const baseShots = Math.floor(totalShots / count);
                const remainder = totalShots % count;
                
                coffeeBeans.forEach((x, i) => {
                    const shots = baseShots + (i < remainder ? 1 : 0);
                    x.amount = shots * 18.0;
                    x.isUserOverridden = false;
                });
            } else {
                coffeeBeans.forEach(x => {
                    x.amount = totalGrams / count;
                    x.isUserOverridden = false;
                });
            }
        }
        const maxIngredients = currentLabMode === 'COFFEE' ? 5 : 4;
        const isDone = selectedIngredients.length >= maxIngredients;
        
        if (currentLabMode === 'COFFEE' && !silent) {
            updateCoffeeChemistryWizard().then(() => {
                updateSelectedArea(isDone);
                if (isDone) {
                    isMixSealed = true;
                    document.getElementById('stepContainer').style.display = 'none';
                    debouncedTriggerFlavorSynthesis();
                } else {
                    debouncedFetchRecommendations();
                    triggerProactiveSuggestion();
                }
            });
        } else if (currentLabMode === 'SODA' && !silent) {
            updateSodaChemistryWizard().then(() => {
                updateSelectedArea(isDone);
                if (isDone) {
                    isMixSealed = true;
                    document.getElementById('stepContainer').style.display = 'none';
                    debouncedTriggerFlavorSynthesis();
                } else {
                    debouncedFetchRecommendations();
                    triggerProactiveSuggestion();
                }
            });
        } else if (currentLabMode === 'SLUSHIE' && !silent) {
            updateCryoChemistryWizard().then(() => {
                updateSelectedArea(isDone);
                if (isDone) {
                    isMixSealed = true;
                    document.getElementById('stepContainer').style.display = 'none';
                    debouncedTriggerFlavorSynthesis();
                } else {
                    debouncedFetchRecommendations();
                    triggerProactiveSuggestion();
                }
            });
        } else {
            updateSelectedArea(isDone);
            if (!silent) {
                if (isDone) {
                    isMixSealed = true;
                    document.getElementById('stepContainer').style.display = 'none';
                    debouncedTriggerFlavorSynthesis();
                } else {
                    debouncedFetchRecommendations();
                    triggerProactiveSuggestion();
                }
            }
        }
    }

    async function surpriseMe() {
        cancelInFlightLLMCalls();
        const btn = document.getElementById('surpriseBtn');
        const originalHtml = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> SYNCING...';

        surpriseController = new AbortController();
        try {
            const response = await fetch('/api/random-pairing/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': window.CSRF_TOKEN
                },
                body: JSON.stringify({ 
                    drink_type: currentLabMode,
                    mode: recommendationMode
                }),
                signal: surpriseController.signal
            });
            const data = await response.json();

            if (data.status === 'success') {
                resetMixer();
                data.ingredients.forEach(ing => {
                    // Use silent = true to prevent flood of AI messages during bulk addition
                    selectIngredient(
                        ing.id, ing.name, ing.intensity, ing.category, 
                        ing.profile || null, true, ing.amount,
                        ing.sweetness || 0, ing.acidity || 0, 
                        ing.bitterness || 0, ing.complexity || 0,
                        ing.type || null,
                        ing.is_ready_to_drink === true || ing.is_ready_to_drink === 'true',
                        ing.is_dry === true || ing.is_dry === 'true'
                    );
                });

                // Display reasoning if AI was used for synthesis
                if (data.reasoning) {
                    const reasoningHtml = `
                        <div class="pe-3">
                            <div class="small fw-bold text-experimental mb-1"><i class="bi bi-robot"></i> AUTONOMOUS DESIGN INTENT</div>
                            <div class="small italic opacity-75">"${data.reasoning}"</div>
                        </div>
                    `;
                    appendChatMessage('assistant', reasoningHtml);
                    aiChatHistory.push({role: 'assistant', content: `Design Intent: ${data.reasoning}`});
                }
                
                // Fetch recommendations and trigger exactly ONE synthesis report
                if (currentLabMode === 'COFFEE') {
                    await updateCoffeeChemistryWizard();
                }
                const maxIngredients = currentLabMode === 'COFFEE' ? 5 : 4;
                updateSelectedArea(selectedIngredients.length >= maxIngredients);
                debouncedFetchRecommendations();
                if (selectedIngredients.length > 0) {
                    debouncedTriggerFlavorSynthesis();
                }
            } else {
                alert(data.error || "Random synthesis failed.");
            }
        } catch (err) {
            if (err.name === 'AbortError') {
                console.log("Random pairing fetch aborted.");
                return;
            }
            console.error(err);
            alert("Comms Failure: Could not reach substrate.");
        } finally {
            surpriseController = null;
            btn.disabled = false;
            btn.innerHTML = originalHtml;
        }
    }

    async function triggerFlavorSynthesis() {
        const reportContainer = document.getElementById('synthesisReportContainer');
        const reportBody = document.getElementById('synthesisReportBody');
        console.log('[Synthesis] triggerFlavorSynthesis called. Mode:', currentLabMode, 'Ingredients:', selectedIngredients.length);
        
        reportContainer.style.display = 'block';
        reportBody.innerHTML = '<div class="text-center py-2"><div class="spinner-border spinner-border-sm text-gradient-lab" role="status"></div><span class="ms-2 small text-dim">Compiling synthesis report...</span></div>';

        try {
            if (currentLabMode === 'COFFEE') {
                let drinkCategory = "Hot Coffee";
                if (coffeeStyle === 'iced') {
                    drinkCategory = "Iced Coffee";
                } else if (coffeeStyle === 'espresso_shot') {
                    drinkCategory = "Pure Espresso / Short Milk";
                }

                const mappedIngredients = selectedIngredients.map((ing, idx) => {
                    const ingCopy = { ...ing };
                    if (ingCopy.type === 'COFFEE_BEAN') {
                        ingCopy.coffee_base_type = coffeeBaseType;
                    }
                    let amount = ing.amount;
                    if (ing.isAiBalanced && ing.aiRatio !== undefined && ing.type !== 'COFFEE_BEAN' && ing.type !== 'DAIRY') {
                        amount = Math.round(coffeeAmountForIngredient(ing, idx, coffeeSizeOz, coffeeBaseType) * ing.aiRatio);
                    } else {
                        amount = coffeeAmountForIngredient(ing, idx, coffeeSizeOz, coffeeBaseType);
                    }
                    ingCopy.amount = amount;
                    ingCopy.ingredient_type = ing.type;
                    return ingCopy;
                });

                const chemistryPromise = fetch('/api/coffee/chemistry/', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': window.CSRF_TOKEN },
                    body: JSON.stringify({
                        drink_category: drinkCategory,
                        cup_size_oz: coffeeSizeOz,
                        espresso_hot_mode: coffeeEspressoHotMode,
                        americano_style: (coffeeStyle === 'hot' && coffeeBaseType === 'espresso' && coffeeEspressoHotMode === 'water'),
                        ingredients: mappedIngredients
                    })
                });

                const aiParams = new URLSearchParams({
                    drink_type: currentLabMode,
                    ingredients: JSON.stringify(mappedIngredients)
                });
                const sseUrl = `/api/ai/synthesize/?${aiParams.toString()}`;

                const chemRes = await chemistryPromise;
                const data = await chemRes.json();
                latestCoffeeChemistryData = data;
                updateSelectedArea(true);

                if (data.recipe_validation) {
                    let validationClass = "bg-success border-success text-success";
                    let validationIcon = "bi-check-circle-fill";
                    if (data.recipe_validation.toLowerCase().includes("warning")) {
                        validationClass = "bg-warning border-warning text-warning";
                        validationIcon = "bi-exclamation-triangle-fill";
                    } else if (data.recipe_validation.toLowerCase().includes("fail")) {
                        validationClass = "bg-danger border-danger text-danger";
                        validationIcon = "bi-x-circle-fill";
                    }

                    let notesHtml = '';
                    if (data.aggregate_base_metrics && data.aggregate_base_metrics.combined_notes && data.aggregate_base_metrics.combined_notes.length > 0) {
                        notesHtml = data.aggregate_base_metrics.combined_notes.map(n => `<span class="badge-fizz bg-secondary text-white me-1 mb-1">${n}</span>`).join('');
                    } else {
                        notesHtml = '<span class="text-dim">None</span>';
                    }

                    const budget = data.drink_metrics.total_liquid_budget_oz || 1.0;
                    const getPct = (vol) => budget > 0 ? ((vol / budget) * 100).toFixed(1) : '0';

                    let baseMixHtml = '';
                    if (data.ingredients && data.ingredients.coffee_base) {
                        const cb = data.ingredients.coffee_base;
                        const shotsText = cb.shots > 0 ? ` (${cb.shots} shot${cb.shots !== 1 ? 's' : ''})` : '';
                        baseMixHtml += `
                            <div class="d-flex justify-content-between align-items-center mb-1">
                                <span class="fw-bold">${cb.name}${shotsText}</span>
                                <span>${cb.volume_oz} oz (${getPct(cb.volume_oz)}%)</span>
                            </div>
                        `;
                    }
                    if (data.ingredients && data.ingredients.base_modifiers && data.ingredients.base_modifiers.length > 0) {
                        baseMixHtml += data.ingredients.base_modifiers.map(bm => `
                            <div class="d-flex justify-content-between align-items-center mb-1">
                                <span class="fw-bold">${bm.name}</span>
                                <span>${bm.volume_oz} oz (${getPct(bm.volume_oz)}%)</span>
                            </div>
                        `).join('');
                    }
                    if (!baseMixHtml) {
                        baseMixHtml = '<div class="text-dim">None</div>';
                    }

                    let dairyHtml = '';
                    if (data.ingredients && data.ingredients.payload_filler) {
                        const pf = data.ingredients.payload_filler;
                        if (pf.name !== 'None') {
                            if (pf.is_corrected) {
                                const pri_vol_ml = Math.round(pf.primary_volume_oz * 29.5735);
                                const tex_vol_ml = Math.round(pf.texturizer_volume_oz * 29.5735);
                                let displayName = pf.primary_name;
                                const matchedIng = selectedIngredients.find(ing => ing.id == pf.id);
                                if (matchedIng) {
                                    displayName = matchedIng.name;
                                }
                                dairyHtml = `
                                    <div class="d-flex justify-content-between align-items-center mb-1">
                                        <span class="fw-bold">${displayName}: ${pri_vol_ml}ml (Primary Filler)</span>
                                        <span>${pf.primary_volume_oz.toFixed(2)} oz (${getPct(pf.primary_volume_oz)}%)</span>
                                    </div>
                                    <div class="d-flex justify-content-between align-items-center mb-1">
                                        <span class="fw-bold">${pf.texturizer_name}: ${tex_vol_ml}ml (Texture Anchor)</span>
                                        <span>${pf.texturizer_volume_oz.toFixed(2)} oz (${getPct(pf.texturizer_volume_oz)}%)</span>
                                    </div>
                                `;
                            } else {
                                let displayName = pf.name;
                                const matchedIng = selectedIngredients.find(ing => ing.id == pf.id);
                                if (matchedIng) {
                                    displayName = matchedIng.name;
                                }
                                dairyHtml = `
                                    <div class="d-flex justify-content-between align-items-center mb-1">
                                        <span class="fw-bold">${displayName}</span>
                                        <span>${pf.volume_oz} oz (${getPct(pf.volume_oz)}%)</span>
                                    </div>
                                `;
                            }
                        } else {
                            dairyHtml = '<div class="text-dim">None</div>';
                        }
                    }

                    let modifiersHtml = '';
                    if (data.ingredients && data.ingredients.flavor_modifiers && data.ingredients.flavor_modifiers.length > 0) {
                        modifiersHtml = data.ingredients.flavor_modifiers.map(m => {
                            let displayName = m.name;
                            const matchedIng = selectedIngredients.find(ing => ing.id == m.id);
                            if (matchedIng) {
                                const role = m.name.match(/\((Dominant|Accent)\)$/i);
                                const roleSuffix = role ? ` ${role[0]}` : '';
                                displayName = `${matchedIng.name}${roleSuffix}`;
                            }
                            return `
                                <div class="d-flex justify-content-between align-items-center mb-1">
                                    <span class="fw-bold">${displayName}</span>
                                    <span>${m.volume_oz} oz (${getPct(m.volume_oz)}%)</span>
                                </div>
                            `;
                        }).join('');
                    } else {
                        modifiersHtml = '<div class="text-dim">None</div>';
                    }

                    let prepStepsHtml = '';
                    if (data.preparation_steps && data.preparation_steps.length > 0) {
                        prepStepsHtml = `
                            <div class="border-top border-white border-opacity-10 pt-3 mb-3 animate-fade-in">
                                <h6 class="readout-label text-gradient-lab mb-2">PREPARATION STEPS (SOLUBILITY)</h6>
                                <ol class="small text-white opacity-90 ps-3 mb-0">
                                    ${data.preparation_steps.map(step => `<li class="mb-1">${step}</li>`).join('')}
                                </ol>
                            </div>
                        `;
                    }

                    reportBody.innerHTML = `
                        <div class="card bg-dark bg-opacity-50 border-white border-opacity-10 rounded-3 mb-3">
                            <div class="card-body p-3">
                                <div class="alert ${validationClass} bg-opacity-10 border border-opacity-20 d-flex align-items-center gap-2 mb-3">
                                    <i class="bi ${validationIcon}"></i>
                                    <div class="fw-bold small">${data.recipe_validation}</div>
                                </div>

                                <div class="row g-3 mb-3">
                                    <div class="col-md-6">
                                        <h6 class="readout-label text-gradient-lab mb-2">CHEMISTRY METRICS</h6>
                                        <div class="d-flex flex-column gap-1 small">
                                            <div class="d-flex justify-content-between"><span>Body Intensity</span> <span class="fw-bold">${data.aggregate_base_metrics.calculated_body}/5.0</span></div>
                                            <div class="d-flex justify-content-between"><span>Acidity Score</span> <span class="fw-bold">${data.aggregate_base_metrics.calculated_acidity}/5.0</span></div>
                                            <div class="d-flex justify-content-between"><span>Bitterness Score</span> <span class="fw-bold">${data.aggregate_base_metrics.calculated_bitterness}/5.0</span></div>
                                            <div class="mt-2">
                                                <span class="d-block text-dim mb-1" style="font-size: 0.65rem;">COMBINED FLAVOR NOTES</span>
                                                <div class="d-flex flex-wrap">${notesHtml}</div>
                                            </div>
                                        </div>
                                    </div>
                                    <div class="col-md-6">
                                        <h6 class="readout-label text-gradient-lab mb-2">VOLUMETRIC BUDGETS</h6>
                                        <div class="d-flex flex-column gap-1 small">
                                            <div class="d-flex justify-content-between"><span>Drink Category</span> <span class="fw-bold">${drinkCategory}</span></div>
                                            <div class="d-flex justify-content-between"><span>Target Cup Size</span> <span class="fw-bold">${coffeeSizeOz} oz</span></div>
                                            <div class="d-flex justify-content-between"><span>Liquid Budget</span> <span class="fw-bold">${data.liquid_budget_oz} oz</span></div>
                                            <div class="d-flex justify-content-between"><span>Ice Volume</span> <span class="fw-bold">${data.ice_volume_oz} oz</span></div>
                                        </div>
                                    </div>
                                </div>

                                <div class="border-top border-white border-opacity-10 pt-3 mb-3">
                                    <h6 class="readout-label text-gradient-lab mb-2">CALCULATED EXTRACTION RATIOS</h6>
                                    <div class="small">
                                        <div class="mb-2">
                                            <span class="text-dim d-block mb-1" style="font-size: 0.65rem;">COFFEE BASE MIX</span>
                                            ${baseMixHtml}
                                        </div>
                                        <div class="mb-2">
                                            <span class="text-dim d-block mb-1" style="font-size: 0.65rem;">DAIRY / FILLER</span>
                                            ${dairyHtml}
                                        </div>
                                        <div>
                                            <span class="text-dim d-block mb-1" style="font-size: 0.65rem;">FLAVOR MODIFIERS</span>
                                            ${modifiersHtml}
                                        </div>
                                    </div>
                                </div>

                                <div class="border-top border-white border-opacity-10 pt-3">
                                    <h6 class="readout-label text-gradient-lab mb-1">BARISTA RECOMMENDATIONS</h6>
                                    <p class="mb-0 italic small text-dim mb-3">"${data.barista_notes}"</p>
                                </div>

                                ${prepStepsHtml}

                                <div class="border-top border-white border-opacity-10 pt-3">
                                    <h6 class="readout-label text-gradient-lab mb-1">OVERALL PROFILE DESCRIPTION</h6>
                                    <div class="mb-0 small text-white opacity-90" style="white-space: pre-line;" id="aiProfileContainer">
                                        <span id="aiProfileText"></span>
                                        <div id="aiProfileSpinner" class="mt-2">
                                            <div class="spinner-border spinner-border-sm text-gradient-lab" role="status"></div>
                                            <span class="ms-2 text-dim small">Synthesizing profile...</span>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    `;
                    
                    // Native SSE consumption (replaces HTMX)
                    const eventSource = new EventSource(sseUrl);
                    
                    eventSource.addEventListener('message', function(e) {
                        const textSpan = reportBody.querySelector('#aiProfileText');
                        if (textSpan) {
                            textSpan.innerHTML += e.data;
                        }
                    });
                    
                    eventSource.addEventListener('remove_spinner', function(e) {
                        const spinner = reportBody.querySelector('#aiProfileSpinner');
                        if (spinner) spinner.remove();
                        eventSource.close();
                    });
                    
                    eventSource.onerror = function(e) {
                        const spinner = reportBody.querySelector('#aiProfileSpinner');
                        if (spinner) spinner.remove();
                        eventSource.close();
                    };

                    // Scroll to report
                    reportContainer.scrollIntoView({ behavior: 'smooth', block: 'end' });
                } else {
                    reportBody.innerHTML = `<div class="text-warning small">Chemistry compilation failed.</div>`;
                }
            } else if (currentLabMode === 'SODA') {
                const mappedIngredients = selectedIngredients.map((ing) => {
                    const ingCopy = { ...ing };
                    ingCopy.ingredient_type = ing.type || ing.ingredient_type;
                    ingCopy.is_primary = ing.isPrimary || false;
                    return ingCopy;
                });

                const chemistryPromise = fetch('/api/soda/chemistry/', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': window.CSRF_TOKEN },
                    body: JSON.stringify({
                        sweetness_style: sodaSweetnessStyle,
                        bottle_scale: bottleScale,
                        ingredients: mappedIngredients
                    })
                });

                const aiParams = new URLSearchParams({
                    drink_type: currentLabMode,
                    ingredients: JSON.stringify(mappedIngredients)
                });
                const sseUrl = `/api/ai/synthesize/?${aiParams.toString()}`;

                const chemRes = await chemistryPromise;
                const data = await chemRes.json();
                latestSodaChemistryData = data;
                updateSelectedArea(true);

                if (data.recipe_validation) {
                    let validationClass = "bg-success border-success text-success";
                    let validationIcon = "bi-check-circle-fill";
                    if (data.recipe_validation.toLowerCase().includes("warning")) {
                        validationClass = "bg-warning border-warning text-warning";
                        validationIcon = "bi-exclamation-triangle-fill";
                    } else if (data.recipe_validation.toLowerCase().includes("fail")) {
                        validationClass = "bg-danger border-danger text-danger";
                        validationIcon = "bi-x-circle-fill";
                    }

                    // Water card volume detail
                    let waterHtml = '';
                    if (data.ingredients && data.ingredients.carbonated_water) {
                        const cw = data.ingredients.carbonated_water;
                        waterHtml = `
                            <div class="d-flex justify-content-between align-items-center mb-1">
                                <span class="fw-bold">${cw.name}</span>
                                <span>${cw.volume_ml} ml</span>
                            </div>
                        `;
                    }

                    // Syrups list
                    let modifiersHtml = '';
                    if (data.ingredients && data.ingredients.modifiers && data.ingredients.modifiers.length > 0) {
                        modifiersHtml = data.ingredients.modifiers.map(m => `
                            <div class="d-flex justify-content-between align-items-center mb-1">
                                <span class="fw-bold">${m.name} (${m.role})</span>
                                <span>${m.volume_ml} ml (${m.percentage_of_syrup}%)</span>
                            </div>
                        `).join('');
                    } else {
                        modifiersHtml = '<div class="text-dim">None</div>';
                    }

                    let prepStepsHtml = '';
                    if (data.preparation_steps && data.preparation_steps.length > 0) {
                        prepStepsHtml = `
                            <div class="border-top border-white border-opacity-10 pt-3 mb-3 animate-fade-in">
                                <h6 class="readout-label text-gradient-lab mb-2">PREPARATION STEPS</h6>
                                <ol class="small text-white opacity-90 ps-3 mb-0">
                                    ${data.preparation_steps.map(step => `<li class="mb-1">${step}</li>`).join('')}
                                </ol>
                            </div>
                        `;
                    }

                    let targetLabel = '';
                    if (Math.abs(bottleScale - 1.0) < 0.01) targetLabel = '1.0L Bottle';
                    else if (Math.abs(bottleScale - 0.5) < 0.01) targetLabel = '0.5L Bottle';
                    else if (Math.abs(bottleScale - 0.355) < 0.01) targetLabel = '12oz Glass';

                    reportBody.innerHTML = `
                        <div class="card bg-dark bg-opacity-50 border-white border-opacity-10 rounded-3 mb-3">
                            <div class="card-body p-3">
                                <div class="alert ${validationClass} bg-opacity-10 border border-opacity-20 d-flex align-items-center gap-2 mb-3">
                                    <i class="bi ${validationIcon}"></i>
                                    <div class="fw-bold small">${data.recipe_validation}</div>
                                </div>

                                <div class="row g-3 mb-3">
                                    <div class="col-md-6">
                                        <h6 class="readout-label text-gradient-lab mb-2">CHEMISTRY METRICS</h6>
                                        <div class="d-flex flex-column gap-1 small">
                                            <div class="d-flex justify-content-between"><span>Sweetness Rating</span> <span class="fw-bold">${data.extraction_analysis.sweetness}/5.0</span></div>
                                            <div class="d-flex justify-content-between"><span>Acidity Score</span> <span class="fw-bold">${data.extraction_analysis.acidity}/5.0</span></div>
                                            <div class="d-flex justify-content-between"><span>Bitterness Score</span> <span class="fw-bold">${data.extraction_analysis.bitterness}/5.0</span></div>
                                        </div>
                                    </div>
                                    <div class="col-md-6">
                                        <h6 class="readout-label text-gradient-lab mb-2">VOLUMETRIC BUDGETS</h6>
                                        <div class="d-flex flex-column gap-1 small">
                                            <div class="d-flex justify-content-between"><span>Sweetness Style</span> <span class="fw-bold">${data.drink_metrics.sweetness_style}</span></div>
                                            <div class="d-flex justify-content-between"><span>Batch Scale</span> <span class="fw-bold">${targetLabel}</span></div>
                                            <div class="d-flex justify-content-between"><span>Carbonated Water</span> <span class="fw-bold">${data.drink_metrics.water_volume_ml} ml</span></div>
                                            <div class="d-flex justify-content-between"><span>Total Syrup Volume</span> <span class="fw-bold">${data.drink_metrics.total_syrup_volume_ml} ml / ${data.drink_metrics.maximum_syrup_limit_ml} ml max</span></div>
                                        </div>
                                    </div>
                                </div>

                                <div class="border-top border-white border-opacity-10 pt-3 mb-3">
                                    <h6 class="readout-label text-gradient-lab mb-2">CALCULATED EXTRACTS</h6>
                                    <div class="small">
                                        <div class="mb-2">
                                            <span class="text-dim d-block mb-1" style="font-size: 0.65rem;">WATER BASE</span>
                                            ${waterHtml}
                                        </div>
                                        <div>
                                            <span class="text-dim d-block mb-1" style="font-size: 0.65rem;">MONIN FLAVOR SYRUPS</span>
                                            ${modifiersHtml}
                                        </div>
                                    </div>
                                </div>

                                <div class="border-top border-white border-opacity-10 pt-3">
                                    <h6 class="readout-label text-gradient-lab mb-1">MIXOLOGIST NOTES</h6>
                                    <p class="mb-0 italic small text-dim mb-3">"${data.barista_notes}"</p>
                                </div>

                                ${prepStepsHtml}

                                <div class="border-top border-white border-opacity-10 pt-3">
                                    <h6 class="readout-label text-gradient-lab mb-1">OVERALL PROFILE DESCRIPTION</h6>
                                    <div class="mb-0 small text-white opacity-90" style="white-space: pre-line;" id="aiProfileContainer">
                                        <span id="aiProfileText"></span>
                                        <div id="aiProfileSpinner" class="mt-2">
                                            <div class="spinner-border spinner-border-sm text-gradient-lab" role="status"></div>
                                            <span class="ms-2 text-dim small">Synthesizing profile...</span>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    `;
                    
                    // Native SSE consumption (replaces HTMX)
                    const eventSource = new EventSource(sseUrl);
                    
                    eventSource.addEventListener('message', function(e) {
                        const textSpan = reportBody.querySelector('#aiProfileText');
                        if (textSpan) {
                            textSpan.innerHTML += e.data;
                        }
                    });
                    
                    eventSource.addEventListener('remove_spinner', function(e) {
                        const spinner = reportBody.querySelector('#aiProfileSpinner');
                        if (spinner) spinner.remove();
                        eventSource.close();
                    });
                    
                    eventSource.onerror = function(e) {
                        const spinner = reportBody.querySelector('#aiProfileSpinner');
                        if (spinner) spinner.remove();
                        eventSource.close();
                    };

                    // Scroll to report
                    reportContainer.scrollIntoView({ behavior: 'smooth', block: 'end' });
                } else {
                    reportBody.innerHTML = `<div class="text-warning small">Chemistry compilation failed.</div>`;
                }
            } else if (currentLabMode === 'SLUSHIE') {
                const mappedIngredients = selectedIngredients.map((ing) => {
                    const ingCopy = { ...ing };
                    ingCopy.ingredient_type = ing.type || ing.ingredient_type;
                    return ingCopy;
                });

                const chemistryPromise = fetch('/api/cryo/chemistry/', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': window.CSRF_TOKEN },
                    body: JSON.stringify({
                        bottle_scale: bottleScale,
                        ingredients: mappedIngredients
                    })
                });

                const aiParams = new URLSearchParams({
                    drink_type: currentLabMode,
                    ingredients: JSON.stringify(mappedIngredients)
                });
                const sseUrl = `/api/ai/synthesize/?${aiParams.toString()}`;

                const chemRes = await chemistryPromise;
                const data = await chemRes.json();
                latestCryoChemistryData = data;
                updateSelectedArea(true);

                if (data.recipe_validation) {
                    let validationClass = "bg-success border-success text-success";
                    let validationIcon = "bi-check-circle-fill";
                    if (data.recipe_validation.toLowerCase().includes("warning")) {
                        validationClass = "bg-warning border-warning text-warning";
                        validationIcon = "bi-exclamation-triangle-fill";
                    } else if (data.recipe_validation.toLowerCase().includes("fail")) {
                        validationClass = "bg-danger border-danger text-danger";
                        validationIcon = "bi-x-circle-fill";
                    }

                    // Filler card volume detail
                    let fillerHtml = '';
                    if (data.ingredients && data.ingredients.filler) {
                        const filler = data.ingredients.filler;
                        fillerHtml = `
                            <div class="d-flex justify-content-between align-items-center mb-1">
                                <span class="fw-bold">${filler.name}</span>
                                <span>${filler.volume_ml.toFixed(1)} ml</span>
                            </div>
                        `;
                    }

                    // Syrups list
                    let modifiersHtml = '';
                    if (data.ingredients && data.ingredients.modifiers && data.ingredients.modifiers.length > 0) {
                        modifiersHtml = data.ingredients.modifiers.map(m => `
                            <div class="d-flex justify-content-between align-items-center mb-1">
                                <span class="fw-bold">${m.name}</span>
                                <span>${m.volume_ml.toFixed(1)} ml (${m.percentage_of_batch}%)</span>
                            </div>
                        `).join('');
                    } else {
                        modifiersHtml = '<div class="text-dim">None</div>';
                    }

                    let prepStepsHtml = '';
                    if (data.preparation_steps && data.preparation_steps.length > 0) {
                        const updatedSteps = data.preparation_steps.map(step => {
                            if (currentLabMode === 'SLUSHIE' && step.startsWith("Step 2:") && data.ingredients && data.ingredients.filler) {
                                return `Step 2: Add exactly ${data.ingredients.filler.volume_ml.toFixed(1)}ml of ${data.ingredients.filler.name} to the pitcher. Whisk vigorously for 30-45 seconds to achieve full molecular suspension.`;
                            }
                            return step;
                        });
                        prepStepsHtml = `
                            <div class="border-top border-white border-opacity-10 pt-3 mb-3 animate-fade-in">
                                <h6 class="readout-label text-gradient-lab mb-2">PREPARATION STEPS (SOLUBILITY & FREEZING)</h6>
                                <ol class="small text-white opacity-90 ps-3 mb-0">
                                    ${updatedSteps.map(step => `<li class="mb-1">${step}</li>`).join('')}
                                </ol>
                            </div>
                        `;
                    }

                    let targetLabel = '';
                    if (Math.abs(bottleScale - 0.5) < 0.01) targetLabel = '16oz Batch (473ml)';
                    else if (Math.abs(bottleScale - 1.0) < 0.01) targetLabel = '32oz Batch (946ml)';
                    else if (Math.abs(bottleScale - 1.5) < 0.01) targetLabel = '48oz Batch (1420ml)';
                    else if (Math.abs(bottleScale - 2.0) < 0.01) targetLabel = '64oz Batch (1892ml)';

                    reportBody.innerHTML = `
                        <div class="card bg-dark bg-opacity-50 border-white border-opacity-10 rounded-3 mb-3">
                            <div class="card-body p-3">
                                <div class="alert ${validationClass} bg-opacity-10 border border-opacity-20 d-flex align-items-center gap-2 mb-3">
                                    <i class="bi ${validationIcon}"></i>
                                    <div class="fw-bold small">${data.recipe_validation}</div>
                                </div>

                                <div class="row g-3 mb-3">
                                    <div class="col-md-6">
                                        <h6 class="readout-label text-gradient-lab mb-2">FREEZING PHYSICS METRICS</h6>
                                        <div class="d-flex flex-column gap-1 small">
                                            <div class="d-flex justify-content-between"><span>Sugar Density (Brix)</span> <span class="fw-bold">${data.drink_metrics.achieved_brix}% Brix</span></div>
                                            <div class="d-flex justify-content-between"><span>Perceived Sweetness</span> <span class="fw-bold">${data.extraction_analysis.sweetness}/5.0</span></div>
                                            <div class="d-flex justify-content-between"><span>Acidity Score</span> <span class="fw-bold">${data.extraction_analysis.acidity}/5.0</span></div>
                                            <div class="d-flex justify-content-between"><span>Bitterness Score</span> <span class="fw-bold">${data.extraction_analysis.bitterness}/5.0</span></div>
                                        </div>
                                    </div>
                                    <div class="col-md-6">
                                        <h6 class="readout-label text-gradient-lab mb-2">VOLUMETRIC BUDGETS</h6>
                                        <div class="d-flex flex-column gap-1 small">
                                            <div class="d-flex justify-content-between"><span>Batch Scale Target</span> <span class="fw-bold">${targetLabel}</span></div>
                                            <div class="d-flex justify-content-between"><span>Total Liquid Inputs</span> <span class="fw-bold">${data.drink_metrics.target_volume_ml} ml</span></div>
                                            <div class="d-flex justify-content-between"><span>Dynamic Volume Filler</span> <span class="fw-bold">${data.drink_metrics.filler_volume_ml} ml</span></div>
                                            <div class="d-flex justify-content-between"><span>Total Modifiers Volume</span> <span class="fw-bold">${data.drink_metrics.total_syrup_volume_ml} ml</span></div>
                                        </div>
                                    </div>
                                </div>

                                <div class="border-top border-white border-opacity-10 pt-3 mb-3">
                                    <h6 class="readout-label text-gradient-lab mb-2">CALCULATED EXTRACTS</h6>
                                    <div class="small">
                                        <div class="mb-2">
                                            <span class="text-dim d-block mb-1" style="font-size: 0.65rem;">DYNAMIC VOLUME FILLER</span>
                                            ${fillerHtml}
                                        </div>
                                        <div>
                                            <span class="text-dim d-block mb-1" style="font-size: 0.65rem;">FLAVOR MODIFIERS & SYRUPS</span>
                                            ${modifiersHtml}
                                        </div>
                                    </div>
                                </div>

                                <div class="border-top border-white border-opacity-10 pt-3">
                                    <h6 class="readout-label text-gradient-lab mb-1">MIXOLOGIST NOTES</h6>
                                    <p class="mb-0 italic small text-dim mb-3">"${data.mixologist_notes}"</p>
                                </div>

                                ${prepStepsHtml}

                                <div class="border-top border-white border-opacity-10 pt-3">
                                    <h6 class="readout-label text-gradient-lab mb-1">OVERALL PROFILE DESCRIPTION</h6>
                                    <div class="mb-0 small text-white opacity-90" style="white-space: pre-line;" id="aiProfileContainer">
                                        <span id="aiProfileText"></span>
                                        <div id="aiProfileSpinner" class="mt-2">
                                            <div class="spinner-border spinner-border-sm text-gradient-lab" role="status"></div>
                                            <span class="ms-2 text-dim small">Synthesizing profile...</span>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    `;
                    
                    // Native SSE consumption (replaces HTMX)
                    const eventSource = new EventSource(sseUrl);
                    
                    eventSource.addEventListener('message', function(e) {
                        const textSpan = reportBody.querySelector('#aiProfileText');
                        if (textSpan) {
                            textSpan.innerHTML += e.data;
                        }
                    });
                    
                    eventSource.addEventListener('remove_spinner', function(e) {
                        const spinner = reportBody.querySelector('#aiProfileSpinner');
                        if (spinner) spinner.remove();
                        eventSource.close();
                    });
                    
                    eventSource.onerror = function(e) {
                        const spinner = reportBody.querySelector('#aiProfileSpinner');
                        if (spinner) spinner.remove();
                        eventSource.close();
                    };

                    // Scroll to report
                    reportContainer.scrollIntoView({ behavior: 'smooth', block: 'end' });
                } else {
                    reportBody.innerHTML = `<div class="text-warning small">Chemistry compilation failed.</div>`;
                }
            } else {
                const aiParams = new URLSearchParams({
                    drink_type: currentLabMode,
                    ingredients: JSON.stringify(selectedIngredients)
                });
                const sseUrl = `/api/ai/synthesize/?${aiParams.toString()}`;

                reportBody.innerHTML = `
                    <div class="mb-0 small text-white opacity-90" style="white-space: pre-line;" id="aiProfileContainer">
                        <span id="aiProfileText"></span>
                        <div id="aiProfileSpinner" class="mt-2">
                            <div class="spinner-border spinner-border-sm text-gradient-lab" role="status"></div>
                            <span class="ms-2 text-dim small">Synthesizing profile...</span>
                        </div>
                    </div>
                `;
                
                // Native SSE consumption (replaces HTMX)
                const eventSource = new EventSource(sseUrl);
                
                eventSource.addEventListener('message', function(e) {
                    const textSpan = reportBody.querySelector('#aiProfileText');
                    if (textSpan) {
                        textSpan.innerHTML += e.data;
                    }
                });
                
                eventSource.addEventListener('remove_spinner', function(e) {
                    const spinner = reportBody.querySelector('#aiProfileSpinner');
                    if (spinner) spinner.remove();
                    eventSource.close();
                });
                
                eventSource.onerror = function(e) {
                    const spinner = reportBody.querySelector('#aiProfileSpinner');
                    if (spinner) spinner.remove();
                    eventSource.close();
                };

                // Scroll to report
                reportContainer.scrollIntoView({ behavior: 'smooth', block: 'end' });
            }
        } catch (err) {
            console.error('[Synthesis] FATAL ERROR in triggerFlavorSynthesis:', err);
            reportBody.innerHTML = `<div class="text-danger small">Connectivity Error: Could not reach the synthesis substrate.</div>
                                   <button class="btn btn-xs btn-outline-warning mt-2 w-100" onclick="triggerFlavorSynthesis()">Retry Synthesis</button>`;
        }
    }

    // Global click handler for reagent selection
    document.addEventListener('click', function(e) {
        const btn = e.target.closest('.select-ingredient-btn');
        if (btn) {
            console.log("Laboratory Click Detected on:", btn.dataset.name);
            selectIngredient(
                btn.dataset.id,
                btn.dataset.name,
                btn.dataset.intensity,
                btn.dataset.category,
                btn.dataset.profile || null,
                false,
                btn.dataset.amount || null,
                btn.dataset.sweetness || 0,
                btn.dataset.acidity || 0,
                btn.dataset.bitterness || 0,
                btn.dataset.complexity || 0,
                btn.dataset.type || null,
                btn.dataset.isReadyToDrink === 'true',
                btn.dataset.isDry === 'true',
                btn.dataset.roastLevel || null,
                btn.dataset.flavorNotes || '',
                btn.dataset.isDecaf === 'true'
            );
        }
    });

    function partitionBases() {
        const recommendedList = document.getElementById('recommendedBasesList');
        const unorthodoxList = document.getElementById('unorthodoxBasesList');
        const recommendedTitle = document.getElementById('recommendedBasesTitle');
        const unorthodoxTitle = document.getElementById('unorthodoxBasesTitle');
        
        recommendedList.innerHTML = '';
        unorthodoxList.innerHTML = '';
        
        const isExperimental = (recommendationMode === 'experimental');
        const isWaterBaseStep2 = (currentLabMode === 'SLUSHIE' && selectedIngredients.length === 1 && selectedIngredients[0].id === 'virtual_water');
        
        // Temporarily render cards into a hidden element to parse them
        const tempDiv = document.createElement('div');
        tempDiv.innerHTML = allIngredientsHtml;
        
        const cards = Array.from(tempDiv.querySelectorAll('.ingredient-card'));
        
        let recommendedCount = 0;
        let unorthodoxCount = 0;
        
        if (currentLabMode === 'SLUSHIE' && !isWaterBaseStep2) {
            const col = document.createElement('div');
            col.className = 'col-md-4 col-sm-6 ingredient-card';
            col.setAttribute('data-type', 'OTHER');
            col.setAttribute('data-systems', 'SLUSHIE');
            col.innerHTML = `
                <div class="glass-card p-3 h-100 d-flex flex-column align-items-center justify-content-center text-center cursor-pointer select-ingredient-btn"
                     data-id="virtual_water"
                     data-type="OTHER"
                     data-name="Water"
                     data-intensity="1"
                     data-sweetness="0"
                     data-acidity="0"
                     data-bitterness="0"
                     data-complexity="0"
                     data-base-suitability="5.0"
                     data-accent-suitability="1.0"
                     data-category="neutral"
                     data-is-ready-to-drink="true"
                     data-profile=''>
                    <span class="fw-bold fs-5 mb-2">Water</span>
                    <span class="badge-fizz bg-neutral">neutral</span>
                    <div class="d-flex justify-content-between w-100 mt-2 px-1 border-top border-white border-opacity-5 pt-2" style="font-size: 0.65rem;">
                        <span class="text-gradient-lab font-monospace">B: 5.0</span>
                        <span class="text-experimental font-monospace">A: 1.0</span>
                    </div>
                </div>
            `;
            recommendedList.appendChild(col);
            recommendedCount++;
        }
        
        cards.forEach(card => {
            const type = card.getAttribute('data-type');
            const systems = card.getAttribute('data-systems') || "SODA,COFFEE,SLUSHIE";
            const systemList = systems.split(',');
            
            const btn = card.querySelector('.select-ingredient-btn');
            const isReadyToDrink = btn ? btn.getAttribute('data-is-ready-to-drink') === 'true' : false;
            
            let isTypeMatch = false;
            if (currentLabMode === 'SODA') {
                isTypeMatch = (type === 'SODA_SYRUP' || type === 'OTHER');
            } else if (currentLabMode === 'COFFEE') {
                isTypeMatch = (type === 'COFFEE_BEAN');
            } else if (currentLabMode === 'SLUSHIE') {
                if (isWaterBaseStep2) {
                    isTypeMatch = (type === 'SODA_SYRUP' || type === 'OTHER') && !isReadyToDrink;
                } else {
                    isTypeMatch = (type === 'SODA_SYRUP' || type === 'OTHER') && isReadyToDrink;
                }
            }
            
            const isSystemMatch = systemList.map(s => s.trim()).includes(currentLabMode);
            let shouldShow = isExperimental ? true : (isTypeMatch && isSystemMatch);
            if (currentLabMode === 'SLUSHIE') {
                if (isWaterBaseStep2) {
                    shouldShow = shouldShow && !isReadyToDrink;
                } else {
                    shouldShow = shouldShow && isReadyToDrink;
                }
            }
            
            if (shouldShow) {
                const btn = card.querySelector('.select-ingredient-btn');
                if (!btn) return;
                const baseScore = parseFloat(btn.getAttribute('data-base-suitability') || '3.0');
                const accentScore = parseFloat(btn.getAttribute('data-accent-suitability') || '3.0');
                
                // Recreate card wrapper
                const col = document.createElement('div');
                col.className = 'col-md-4 col-sm-6 ingredient-card';
                col.setAttribute('data-type', type);
                col.setAttribute('data-systems', systems);
                col.innerHTML = card.innerHTML;
                
                if (isExperimental) {
                    // Experimental Mode: promote low base suitability (unorthodox)
                    if (baseScore < 3.5) {
                        recommendedList.appendChild(col);
                        recommendedCount++;
                    } else {
                        unorthodoxList.appendChild(col);
                        unorthodoxCount++;
                    }
                } else {
                    // Standard Mode: traditional/safe bases (base_suitability >= 3.5)
                    if (baseScore >= 3.5) {
                        recommendedList.appendChild(col);
                        recommendedCount++;
                    } else {
                        unorthodoxList.appendChild(col);
                        unorthodoxCount++;
                    }
                }
            }
        });
        
        // Show/hide groups based on count
        document.getElementById('recommendedBasesGroup').style.display = recommendedCount > 0 ? 'block' : 'none';
        document.getElementById('unorthodoxBasesGroup').style.display = unorthodoxCount > 0 ? 'block' : 'none';
        
        // Update titles
        if (isWaterBaseStep2) {
            recommendedTitle.innerHTML = '<i class="bi bi-shield-check text-gradient-lab me-2"></i>RECOMMENDED SYRUP BASES';
            unorthodoxTitle.innerHTML = '<i class="bi bi-exclamation-triangle text-dim me-2"></i>NOT RECOMMENDED / HIGH-INTENSITY SYRUPS';
        } else if (isExperimental) {
            recommendedTitle.innerHTML = '<i class="bi bi-flask text-experimental me-2"></i>RECOMMENDED UNORTHODOX SUBSTRATES';
            unorthodoxTitle.innerHTML = '<i class="bi bi-shield text-dim me-2"></i>STANDARD / SAFE BASES';
        } else {
            recommendedTitle.innerHTML = '<i class="bi bi-shield-check text-gradient-lab me-2"></i>RECOMMENDED BASES';
            unorthodoxTitle.innerHTML = '<i class="bi bi-exclamation-triangle text-dim me-2"></i>NOT RECOMMENDED / HIGH-INTENSITY ACCENTS';
        }

        // Handle empty mode message toggling
        const totalCount = recommendedCount + unorthodoxCount;
        const emptyMsg = document.getElementById('emptyModeMessage');
        const stepHeader = document.getElementById('stepHeader');
        const partitionedBases = document.getElementById('partitionedBasesContainer');

        if (totalCount === 0) {
            if (emptyMsg) emptyMsg.classList.remove('d-none');
                if (emptyMsg) emptyMsg.classList.add('d-none');
                if (stepHeader) stepHeader.classList.remove('d-none');
                if (partitionedBases) partitionedBases.classList.remove('d-none');
            }
        }
        
        function resetMixer() {
            cancelInFlightLLMCalls();
            selectedIngredients = [];
            bottleScale = 1.0;
            latestCoffeeChemistryData = null;
            latestSodaChemistryData = null;
            latestCryoChemistryData = null;
            sodaSweetnessStyle = localStorage.getItem('soda_sweetness_style') || 'CRAFT';
            isMixSealed = false;
            currentStepKey = '';
            stepExcludingIds = [];
            stepExcludingNames = [];

            // Reset sweetness style UI
            ['sweetnessCrisp', 'sweetnessCraft', 'sweetnessFountain'].forEach(id => {
                const el = document.getElementById(id);
                if (el) el.classList.toggle('active-lab-mode', (id === 'sweetnessCrisp' && sodaSweetnessStyle === 'CRISP') || (id === 'sweetnessCraft' && sodaSweetnessStyle === 'CRAFT') || (id === 'sweetnessFountain' && sodaSweetnessStyle === 'FOUNTAIN'));
            });
            
            // Reset soda/slushie scale UI
            ['scale1L', 'scale05L', 'scale12oz'].forEach(id => {
                const el = document.getElementById(id);
                if (el) el.classList.toggle('active-lab-mode', id === 'scale1L');
            });
            ['scale16oz', 'scale32oz', 'scale48oz', 'scale64oz'].forEach(id => {
                const el = document.getElementById(id);
                if (el) el.classList.toggle('active-lab-mode', id === 'scale32oz');
            });
            
            // Reset coffee controls to saved/default state
            const savedStyle = localStorage.getItem('coffee_style') || 'hot';
            const savedSize  = parseFloat(localStorage.getItem('coffee_size_oz') || '12');
            const savedBase  = localStorage.getItem('coffee_base_type') || 'espresso';
            
            // Sync selectors using their setter functions
            setCoffeeStyle(savedStyle);
            if (savedStyle !== 'espresso_shot') {
                setCoffeeSize(savedSize);
            }
            setCoffeeBaseType(savedBase);
            
            document.getElementById('stepContainer').style.display = 'block';
            document.getElementById('stepTitle').textContent = 'Step 1: Select Base Component';
            document.getElementById('synthesisReportContainer').style.display = 'none';
            updateSelectedArea();
            document.getElementById('recommendationContainer').innerHTML = '';
            document.getElementById('partitionedBasesContainer').style.display = 'block';
            partitionBases();
        }

        function stepBack() {
            cancelInFlightLLMCalls();
            if (selectedIngredients.length === 0) return;
            
            selectedIngredients.pop();
            isMixSealed = false;
            document.getElementById('stepContainer').style.display = 'block';
            document.getElementById('synthesisReportContainer').style.display = 'none';
            
            if (currentLabMode === 'COFFEE') {
                updateCoffeeChemistryWizard().then(() => {
                    updateSelectedArea();
                    debouncedFetchRecommendations();
                    
                    if (selectedIngredients.length === 0) {
                        resetMixer();
                    }
                });
            } else if (currentLabMode === 'SODA') {
                updateSodaChemistryWizard().then(() => {
                    updateSelectedArea();
                    debouncedFetchRecommendations();
                    
                    if (selectedIngredients.length === 0) {
                        resetMixer();
                    }
                });
            } else if (currentLabMode === 'SLUSHIE') {
                updateCryoChemistryWizard().then(() => {
                    updateSelectedArea();
                    debouncedFetchRecommendations();
                    
                    if (selectedIngredients.length === 0) {
                        resetMixer();
                    }
                });
            } else {
                updateSelectedArea();
                debouncedFetchRecommendations();
                
                if (selectedIngredients.length === 0) {
                    resetMixer();
                }
            }
        }

        function setPrimaryAnchor(id) {
            selectedIngredients.forEach((ing) => {
                ing.isPrimary = (ing.id == id);
            });
            updateSodaChemistryWizard().then(() => {
                updateSelectedArea();
                if (document.getElementById('synthesisReportContainer').style.display !== 'none') {
                    debouncedTriggerFlavorSynthesis();
                }
            });
        }

        async function fetchRecommendations() {
            if (isMixSealed) {
                document.getElementById('stepContainer').style.display = 'none';
                const lib = document.getElementById('partitionedBasesContainer');
                if (lib) lib.style.display = 'none';
                return;
            }

            if (activeProgressTimer) {
                clearTimeout(activeProgressTimer);
                activeProgressTimer = null;
            }
            activeProgressQueue = [];
            isProcessingProgressQueue = false;

            const ingredientIds = selectedIngredients.map(i => i.id === 'virtual_water' ? 0 : parseInt(i.id));
            const maxIngredients = currentLabMode === 'COFFEE' ? 5 : 4;
            
            const newStepKey = `${currentLabMode}_${recommendationMode}_${engineMode}_${ingredientIds.join(',')}`;
            if (newStepKey !== currentStepKey) {
                currentStepKey = newStepKey;
                stepExcludingIds = [];
                stepExcludingNames = [];
            }
            
            if (ingredientIds.length >= maxIngredients) {
                isMixSealed = true;
                document.getElementById('stepContainer').style.display = 'none';
                const lib = document.getElementById('partitionedBasesContainer');
                if (lib) lib.style.display = 'none';
                updateSelectedArea(true);
                debouncedTriggerFlavorSynthesis();
                return;
            }

            let stepText = '';
            let forceType = null;
            
            if (currentLabMode === 'COFFEE') {
                const coffeeBeansCount = selectedIngredients.filter(x => (x.type || x.ingredient_type || '').toUpperCase() === 'COFFEE_BEAN').length;
                const dairyCount = selectedIngredients.filter(x => (x.type || x.ingredient_type || '').toUpperCase() === 'DAIRY').length;
                const accentsCount = selectedIngredients.length - coffeeBeansCount - dairyCount;
                
                if (coffeeBeansCount === 0) {
                    stepText = 'Step 1: Select Base Component';
                } else if (dairyCount === 0) {
                    stepText = 'Step 2: Select Complementary Payload';
                    forceType = 'DAIRY';
                } else if (accentsCount === 0) {
                    stepText = 'Step 3: Select Flavor Accent';
                } else if (accentsCount === 1) {
                    stepText = 'Step 4: Select Deep Accent';
                } else {
                    stepText = 'Step 5: Select Final Stabilizer';
                }
            } else {
                if (ingredientIds.length === 0) {
                    stepText = 'Step 1: Select Base Component';
                } else if (ingredientIds.length === 1) {
                    if (currentLabMode === 'SLUSHIE' && selectedIngredients[0].id === 'virtual_water') {
                        stepText = 'Step 2: Select Syrup Base';
                    } else {
                        stepText = 'Step 2: Select Complementary Payload';
                    }
                } else if (ingredientIds.length === 2) {
                    stepText = 'Step 3: Select Flavor Accent' + (currentLabMode === 'COFFEE' ? '' : ' (Optional)');
                } else if (ingredientIds.length === 3) {
                    stepText = 'Step 4: Select Deep Accent';
                } else {
                    stepText = 'Step 5: Select Final Stabilizer';
                }
            }
            
            document.getElementById('stepTitle').textContent = stepText;
            const container = document.getElementById('recommendationContainer');
            const library = document.getElementById('partitionedBasesContainer');
            
            const isWaterBaseStep2 = (currentLabMode === 'SLUSHIE' && selectedIngredients.length === 1 && selectedIngredients[0].id === 'virtual_water');
            
            if (ingredientIds.length === 0 || isWaterBaseStep2) {
                container.innerHTML = '';
                library.style.display = 'block';
                partitionBases();
                return;
            }

            container.innerHTML = '<div id="recommendationProgress" class="col-12 text-center py-4"><div class="spinner-border text-gradient-lab" role="status"></div><p id="recommendationProgressText" class="mt-2 text-dim" style="transition: opacity 0.2s ease-in-out; opacity: 1;">Computing molecular affinity...</p></div>';
            library.style.display = 'none'; // Hide library when focused on recommendations

            const isAiEngine = engineMode === 'ai';
            const url = isAiEngine ? '/api/ai/suggest/' : '/api/recommendations/';
            const payload = isAiEngine ? {
                ingredients: selectedIngredients.map(i => i.name),
                drink_type: currentLabMode,
                mode: recommendationMode,
                exclude: stepExcludingNames,
                force_type: forceType,
                stream_html: true
            } : { 
                ingredient_ids: ingredientIds,
                drink_type: currentLabMode,
                mode: recommendationMode,
                exclude_ids: stepExcludingIds,
                force_type: forceType
            };

            if (recommendationsController) {
                recommendationsController.abort();
            }
            const currentController = new AbortController();
            recommendationsController = currentController;

            try {
                const r = await fetch(url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': window.CSRF_TOKEN },
                    body: JSON.stringify(payload),
                    signal: currentController.signal
                });

                let data = null;
                if (isAiEngine) {
                    let isFirstCard = true;
                    window.didStreamCards = false;
                    const reader = r.body.getReader();
                    const decoder = new TextDecoder();
                    let buffer = '';
                    
                    while (true) {
                        const { value, done } = await reader.read();
                        if (done) break;
                        
                        buffer += decoder.decode(value, { stream: true });
                        const lines = buffer.split('\n\n');
                        buffer = lines.pop();
                        
                        for (const chunk of lines) {
                            if (!chunk.trim()) continue;
                            const chunkLines = chunk.split('\n');
                            let eventType = 'message';
                            let dataStr = '';
                            
                            for (const line of chunkLines) {
                                if (line.startsWith('event:')) {
                                    eventType = line.replace('event:', '').trim();
                                } else if (line.startsWith('data:')) {
                                    dataStr = line.substring(5).trim();
                                }
                            }
                            if (eventType === 'message' && dataStr) {
                                window.didStreamCards = true;
                                console.log("Received chunk at " + new Date().toISOString().substring(11, 23) + ":", dataStr);
                                if (isFirstCard) {
                                    isFirstCard = false;
                                    container.innerHTML = `
                                        <div id="ai-cards-container" class="row g-3 row-cols-2 row-cols-md-3 row-cols-lg-5">
                                            ${dataStr}
                                            <div class="ai-loading-placeholder col animate-fade-in"><div class="glass-card p-3 h-100 d-flex flex-column align-items-center justify-content-center text-center border-neural border-opacity-25" style="border-style: dashed;"><div class="spinner-border text-neural spinner-border-sm mb-2" role="status"></div></div></div>
                                            <div class="ai-loading-placeholder col animate-fade-in"><div class="glass-card p-3 h-100 d-flex flex-column align-items-center justify-content-center text-center border-neural border-opacity-25" style="border-style: dashed;"><div class="spinner-border text-neural spinner-border-sm mb-2" role="status"></div></div></div>
                                            <div class="ai-loading-placeholder col animate-fade-in"><div class="glass-card p-3 h-100 d-flex flex-column align-items-center justify-content-center text-center border-neural border-opacity-25" style="border-style: dashed;"><div class="spinner-border text-neural spinner-border-sm mb-2" role="status"></div></div></div>
                                            <div class="ai-loading-placeholder col animate-fade-in"><div class="glass-card p-3 h-100 d-flex flex-column align-items-center justify-content-center text-center border-neural border-opacity-25" style="border-style: dashed;"><div class="spinner-border text-neural spinner-border-sm mb-2" role="status"></div></div></div>
                                        </div>
                                    `;
                                } else {
                                    const placeholders = document.querySelectorAll('.ai-loading-placeholder');
                                    if (placeholders.length > 0) {
                                        placeholders[0].insertAdjacentHTML('beforebegin', dataStr);
                                        if (placeholders.length > 1) {
                                            placeholders[placeholders.length - 1].remove();
                                        }
                                    } else {
                                        const grid = document.getElementById('ai-cards-container');
                                        if (grid) grid.insertAdjacentHTML('beforeend', dataStr);
                                    }
                                }
                            } else if (eventType === 'remove_spinner') {
                                activeProgressQueue.length = 0; // Force clear any pending progress
                                const placeholders = document.querySelectorAll('.ai-loading-placeholder');
                                placeholders.forEach(p => p.remove());
                                const bigSpinner = document.getElementById('recommendationProgress');
                                if (bigSpinner) bigSpinner.remove();
                            } else if (eventType === 'json' && dataStr) {
                                try {
                                    const parsed = JSON.parse(dataStr);
                                    if (parsed.type === 'complete_data' || parsed.status === 'success') {
                                        data = parsed;
                                    }
                                } catch(e) {}
                            } else if (eventType === 'progress' && dataStr) {
                                try {
                                    const parsed = JSON.parse(dataStr);
                                    activeProgressQueue.push(parsed.message);
                                    processActiveProgressQueue();
                                } catch(e) {}
                            } else if (dataStr) {
                                try {
                                    const parsed = JSON.parse(dataStr);
                                    if (parsed.status === 'error') {
                                        throw new Error(parsed.message);
                                    }
                                } catch(e) {}
                            }
                        }
                    }
                    while (isProcessingProgressQueue || activeProgressQueue.length > 0) {
                        await new Promise(resolve => setTimeout(resolve, 50));
                    }
                } else {
                    data = await r.json();
                    container.innerHTML = '';
                }
                
                // Apply Neural Re-balancing to existing ingredients
                if (data && data.rebalancing && Object.keys(data.rebalancing).length > 0) {
                    console.log("Applying Neural Re-balancing:", data.rebalancing);
                    selectedIngredients.forEach((ing, index) => {
                        const ingType = (ing.type || ing.ingredient_type || '').toUpperCase();
                        if (ingType === 'COFFEE_BEAN') {
                            return;
                        }
                        if (ing.isUserOverridden) {
                            return;
                        }
                        const normalizedName = ing.name.toLowerCase().trim();
                        for (const [key, value] of Object.entries(data.rebalancing)) {
                            const normalizedKey = key.toLowerCase().trim();
                            if (normalizedKey === normalizedName ||
                                normalizedName.includes(normalizedKey) ||
                                normalizedKey.includes(normalizedName)) {
                                ing.amount = parseFloat(value);
                                ing.isAiBalanced = true;
                                const standard = coffeeAmountForIngredient(ing, index, coffeeSizeOz, coffeeBaseType);
                                ing.aiRatio = standard > 0 ? (ing.amount / standard) : 1.0;
                                break;
                            }
                        }
                    });
                    updateSelectedArea();
                }

                if (isAiEngine && data && data.reasoning) {
                    const reasoningHtml = `
                        <div class="pe-3">
                            <div class="small fw-bold text-neural mb-1"><i class="bi bi-cpu"></i> NEURAL BALANCE STRATEGY</div>
                            <div class="small italic opacity-75">${data.reasoning}</div>
                        </div>
                    `;
                    appendChatMessage('assistant', reasoningHtml);
                }

                let suggestions = isAiEngine ? (data.suggestions || []) : (data.recommended || []);
                
                // Append these to exclusions for the current step
                suggestions.forEach(rec => {
                    if (!rec.isSeal) {
                        if (rec.id && !stepExcludingIds.includes(parseInt(rec.id))) {
                            stepExcludingIds.push(parseInt(rec.id));
                        }
                        if (rec.name && !stepExcludingNames.includes(rec.name)) {
                            stepExcludingNames.push(rec.name);
                        }
                    }
                });

                
                if (suggestions.length === 0 && !data.seal_recommended) {
                    container.innerHTML = '<div class="col-12 text-center py-4"><p class="text-muted">No ideal matches in lab inventory. <button type="button" class="btn btn-link px-0 text-gradient-lab" onclick="skipOptimization()">Seal current mix</button>.</p></div>';
                    return;
                }


                if (!window.didStreamCards) {
                    const row = document.createElement('div');
                    row.className = 'row g-3 row-cols-2 row-cols-md-3 row-cols-lg-5';
                    
                    suggestions.forEach((rec, idx) => {
                        const col = document.createElement('div');
                        col.className = 'col animate-fade-in';
                        col.style.animationDelay = `${idx * 150}ms`;
                        
                        const badgeClass = getBadgeColor(rec.category);
                        const isExperimentalMode = recommendationMode === 'experimental';
                        
                        let cardClass = 'border-success border-opacity-25';
                        let textClass = 'text-gradient-lab';
                        let iconHtml = '';
                        
                        if (rec.favorite) {
                            cardClass = 'border-favorite glow-favorite';
                            textClass = 'text-warning';
                            iconHtml = '<i class="bi bi-star-fill text-warning me-1" style="filter: drop-shadow(0 0 5px var(--fizz-amber));"></i>';
                        } else if (isExperimentalMode) {
                            cardClass = 'border-experimental glow-experimental';
                            textClass = 'text-experimental';
                            iconHtml = '<i class="bi bi-flask me-1"></i>';
                        } else if (isAiEngine) {
                            cardClass = 'border-neural glow-neural';
                            textClass = 'text-neural';
                            iconHtml = '<i class="bi bi-cpu me-1"></i>';
                        }
                        
                        col.innerHTML = `
                            <div class="glass-card p-3 h-100 d-flex flex-column align-items-center justify-content-center text-center cursor-pointer select-ingredient-btn ${cardClass}"
                                 data-id="${rec.id}" data-name="${rec.name}" data-intensity="${rec.intensity}" data-category="${rec.category}"
                                 data-sweetness="${rec.sweetness}" data-acidity="${rec.acidity}"
                                 data-bitterness="${rec.bitterness}" data-complexity="${rec.complexity}"
                                 data-base-suitability="${rec.base_suitability}" data-accent-suitability="${rec.accent_suitability}"
                                 data-is-ready-to-drink="${rec.is_ready_to_drink}"
                                 data-profile='${JSON.stringify(rec.profile || {})}' data-amount="${rec.amount || ''}" data-type="${rec.type || ''}"
                                 data-favorite="${rec.favorite ? 'true' : 'false'}">
                                    <span class="fw-bold fs-5 mb-1">${rec.favorite ? '★ ' : ''}${rec.name}</span>
                                    <div class="d-flex gap-2 align-items-center mb-2">
                                        <span class="badge-fizz bg-${badgeClass}">${rec.category || ''}</span>
                                    </div>
                                    <div class="d-flex justify-content-between w-100 mt-2 px-1 border-top border-white border-opacity-5 pt-2 mb-2" style="font-size: 0.65rem;">
                                        <span class="text-gradient-lab font-monospace">B: ${rec.base_suitability.toFixed(1)}</span>
                                        <span class="text-experimental font-monospace">A: ${rec.accent_suitability.toFixed(1)}</span>
                                    </div>
                                    <div class="mt-auto">
                                        <small class="${textClass} fw-bold" style="font-size: 0.7rem;">
                                            ${iconHtml}${rec.reason}
                                        </small>
                                    </div>
                            </div>
                        `;
                        row.appendChild(col);
                    });
                    
                    container.appendChild(row);
                }

                const actionsContainer = document.createElement('div');
                actionsContainer.className = 'row g-3 mt-3 rec-actions-container w-100';
                
                let colsHtml = '';
                if (suggestions.length > 0) {
                    colsHtml += `
                        <div class="col-${ingredientIds.length >= 2 ? '6' : '12'}">
                            <div class="glass-card p-3 d-flex flex-column align-items-center justify-content-center text-center cursor-pointer border-white border-opacity-10 w-100" onclick="fetchRecommendations()">
                                <i class="bi bi-arrow-repeat fs-3 mb-1 text-accent animate-spin-hover"></i>
                                <span class="fw-bold small text-uppercase text-accent">Recommend More</span>
                            </div>
                        </div>
                    `;
                }
                if (ingredientIds.length >= 2) {
                    colsHtml += `
                        <div class="col-${suggestions.length > 0 ? '6' : '12'}">
                            <div class="glass-card p-3 d-flex flex-column align-items-center justify-content-center text-center cursor-pointer border-white border-opacity-10 w-100" onclick="skipOptimization()">
                                <i class="bi bi-shield-check fs-3 mb-1 text-success"></i>
                                <span class="fw-bold small text-uppercase">Seal Mix</span>
                            </div>
                        </div>
                    `;
                }
                
                if (colsHtml && !currentController.signal.aborted) {
                    // Remove any existing actions container to prevent duplication
                    const existingActions = container.querySelectorAll('.rec-actions-container');
                    existingActions.forEach(e => e.remove());
                    
                    actionsContainer.innerHTML = colsHtml;
                    container.appendChild(actionsContainer);
                }
                
                // Render recipes
                if (data.recipes && data.recipes.length > 0) {
                    const recContainer = document.getElementById('similarRecipes');
                    if (recContainer) {
                        let recHtml = '';
                        for (const r of data.recipes) {
                            recHtml += `
                                <a href="/ingredients/recipes/${r.id}/" class="fizz-pill bg-dark bg-opacity-50 text-white text-decoration-none border-white border-opacity-10 hover-lime d-flex align-items-center gap-2">
                                    <i class="bi bi-journal-text small"></i> ${r.name}
                                </a>`;
                        }
                        recContainer.innerHTML = recHtml;
                    }
                }
        } catch (err) {
            if (err.name === 'AbortError') {
                return;
            }
            console.error('Synthesis Error:', err);
            container.innerHTML = '<div class="col-12 text-center py-4"><p class="text-danger">Substrate Error: Laboratory signal lost.</p></div>';
        } finally {
            if (recommendationsController === currentController) {
                recommendationsController = null;
            }
        }
    }

    function skipOptimization() {
        isMixSealed = true;
        document.getElementById('stepContainer').style.display = 'none';
        const lib = document.getElementById('partitionedBasesContainer');
        if (lib) lib.style.display = 'none';
        updateSelectedArea(true);
        // Call directly (no debounce) to avoid race conditions with the timeout being cleared
        triggerFlavorSynthesis();
    }

    
// ==========================================
// 3. UI RENDERING & DOM MANIPULATION
// ==========================================
function updateSelectedArea(isDone = false) {
        const unit = 'ml';
        const selectedArea = document.getElementById('selectedArea');
        const list = document.getElementById('selectedIngredientsList');
        const submitArea = document.getElementById('formSubmitArea');
        const maxIngredients = currentLabMode === 'COFFEE' ? 5 : 4;
        
        if (selectedIngredients.length === 0) {
            selectedArea.style.display = 'none';
            submitArea.style.display = 'none';
            return;
        }
        
        selectedArea.style.display = 'block';
        document.getElementById('analyzeBtn').style.display = selectedIngredients.length >= 2 ? 'inline-block' : 'none';
        const scaleContainerSoda = document.getElementById('scaleContainerSoda');
        const scaleContainerCryo = document.getElementById('scaleContainerCryo');
        const scaleContainerCoffee = document.getElementById('scaleContainerCoffee');
        if (currentLabMode === 'SODA') {
            if (scaleContainerSoda) {
                scaleContainerSoda.style.setProperty('display', 'block', 'important');
            }
            if (scaleContainerCryo) {
                scaleContainerCryo.style.setProperty('display', 'none', 'important');
            }
            if (scaleContainerCoffee) {
                scaleContainerCoffee.style.setProperty('display', 'none', 'important');
            }
        } else if (currentLabMode === 'SLUSHIE') {
            if (scaleContainerSoda) {
                scaleContainerSoda.style.setProperty('display', 'none', 'important');
            }
            if (scaleContainerCryo) {
                scaleContainerCryo.style.setProperty('display', 'block', 'important');
            }
            if (scaleContainerCoffee) {
                scaleContainerCoffee.style.setProperty('display', 'none', 'important');
            }
        } else if (currentLabMode === 'COFFEE') {
            if (scaleContainerSoda) {
                scaleContainerSoda.style.setProperty('display', 'none', 'important');
            }
            if (scaleContainerCryo) {
                scaleContainerCryo.style.setProperty('display', 'none', 'important');
            }
            if (scaleContainerCoffee) {
                scaleContainerCoffee.style.setProperty('display', 'block', 'important');
            }
        } else {
            if (scaleContainerSoda) {
                scaleContainerSoda.style.setProperty('display', 'none', 'important');
            }
            if (scaleContainerCryo) {
                scaleContainerCryo.style.setProperty('display', 'none', 'important');
            }
            if (scaleContainerCoffee) {
                scaleContainerCoffee.style.setProperty('display', 'none', 'important');
            }
        }
        
        const hasRtdBase = selectedIngredients.some(ing => ing.isReadyToDrink);
        const firstRtdIndex = selectedIngredients.findIndex(ing => ing.isReadyToDrink);

        let finalWater = 0;

        let allCryoAligned = false;
        if (currentLabMode === 'SLUSHIE' && latestCryoChemistryData && latestCryoChemistryData.ingredients) {
            const list = latestCryoChemistryData.ingredients.modifiers || [];
            allCryoAligned = true;
            selectedIngredients.forEach((ing, index) => {
                const type = (ing.type || ing.ingredient_type || '').toUpperCase();
                const isBase = hasRtdBase && index === firstRtdIndex;
                if (type !== 'COFFEE_BEAN' && type !== 'DAIRY' && ing.id !== 'virtual_water' && !isBase) {
                    const matched = list.find(m => m.id == ing.id);
                    if (!matched) {
                        allCryoAligned = false;
                    }
                }
            });
        }

        let allSodaAligned = false;
        if (currentLabMode === 'SODA' && latestSodaChemistryData && latestSodaChemistryData.ingredients) {
            const list = latestSodaChemistryData.ingredients.modifiers || [];
            allSodaAligned = true;
            selectedIngredients.forEach((ing, index) => {
                const type = (ing.type || ing.ingredient_type || '').toUpperCase();
                const isBase = hasRtdBase && index === firstRtdIndex;
                if (type !== 'COFFEE_BEAN' && type !== 'DAIRY' && ing.id !== 'virtual_water' && !isBase) {
                    const matched = list.find(m => m.id == ing.id);
                    if (!matched) {
                        allSodaAligned = false;
                    }
                }
            });
        }

        let initialTotal = 0;
        let limit = (160 * (bottleScale || 1.0));
        if (currentLabMode === 'SLUSHIE') {
            limit = (189.2 * (bottleScale || 1.0));
        }
        
        // Calculate initial amounts for expansion factor if hasRtdBase is false
        if (!hasRtdBase) {
            selectedIngredients.forEach((ing, index) => {
                let amt = ing.amount;
                const isDry = ing.isDry === true || ing.isDry === 'true' || (currentLabMode === 'COFFEE' && ing.type === 'COFFEE_BEAN');
                if (!amt) {
                    const baseVol = isDry ? 18.0 : (index === 0 ? 80.0 : (index === 1 ? 40.0 : 20.0));
                    amt = baseVol * (bottleScale || 1.0);
                } else if (currentLabMode !== 'COFFEE') {
                    amt = amt * (bottleScale || 1.0);
                }
                if (!isDry) {
                    initialTotal += parseFloat(amt);
                }
            });
        }

        let expansionFactor = 1.0;
        if (!hasRtdBase && initialTotal > 0 && currentLabMode !== 'COFFEE') {
            const isSodaLiters = (currentLabMode === 'SODA' && (Math.abs(bottleScale - 1.0) < 0.01 || Math.abs(bottleScale - 0.5) < 0.01));
            if (isSodaLiters || initialTotal < limit) {
                expansionFactor = limit / initialTotal;
            }
        }

        // Calculate volumes for all ingredients
        let totalSyrup = 0;
        let rtdBaseAmount = 0;
        
        if (allCryoAligned) {
            totalSyrup = latestCryoChemistryData.drink_metrics.total_syrup_volume_ml;
            if (hasRtdBase && latestCryoChemistryData.ingredients && latestCryoChemistryData.ingredients.filler) {
                rtdBaseAmount = latestCryoChemistryData.ingredients.filler.volume_ml;
            }
        } else if (allSodaAligned) {
            totalSyrup = latestSodaChemistryData.drink_metrics.total_syrup_volume_ml;
            if (hasRtdBase && latestSodaChemistryData.ingredients && latestSodaChemistryData.ingredients.carbonated_water) {
                rtdBaseAmount = latestSodaChemistryData.ingredients.carbonated_water.volume_ml;
            }
        } else if (hasRtdBase && currentLabMode !== 'COFFEE') {
            const bottleCapacity = (currentLabMode === 'SODA') ? (bottleScale * 1000) : (bottleScale * 946.35);
            let nonFillerTotal = 0;
            
            selectedIngredients.forEach((ing, index) => {
                if (index !== firstRtdIndex) {
                    let amt = ing.amount;
                    const isDry = ing.isDry === true || ing.isDry === 'true';
                    if (!amt) {
                        const baseVolume = isDry ? 18.0 : (index === 0 ? 80.0 : (index === 1 ? 40.0 : 20.0));
                        amt = baseVolume * (bottleScale || 1.0);
                    } else {
                        amt = amt * (bottleScale || 1.0);
                    }
                    if (!isDry) {
                        nonFillerTotal += parseFloat(amt);
                    }
                }
            });
            
            rtdBaseAmount = Math.max(0, bottleCapacity - nonFillerTotal);
            totalSyrup = nonFillerTotal + rtdBaseAmount;
        } else {
            // Standard soda/slushie expansion logic (when no RTD base)
            selectedIngredients.forEach((ing, index) => {
                let amount = ing.amount;
                const isDry = ing.isDry === true || ing.isDry === 'true';
                if (currentLabMode !== 'COFFEE') {
                    if (!amount) {
                        const baseVolume = isDry ? 18.0 : (index === 0 ? 80.0 : (index === 1 ? 40.0 : 20.0));
                        amount = baseVolume * (bottleScale || 1.0);
                    } else {
                        amount = amount * (bottleScale || 1.0);
                    }
                    if (!isDry) {
                        amount = amount * expansionFactor;
                        totalSyrup += parseFloat(amount);
                    }
                }
            });
        }

        if (currentLabMode === 'SLUSHIE' && hasRtdBase) {
            finalWater = rtdBaseAmount;
        }

        let warningBannerHtml = '';
        if (currentLabMode === 'COFFEE' && latestCoffeeChemistryData && latestCoffeeChemistryData.recipe_validation && latestCoffeeChemistryData.recipe_validation !== 'Pass') {
            let alertClass = 'alert-warning border-warning text-warning';
            let iconClass = 'bi-exclamation-triangle-fill';
            if (latestCoffeeChemistryData.recipe_validation.toLowerCase().includes('fail')) {
                alertClass = 'alert-danger border-danger text-danger';
                iconClass = 'bi-x-circle-fill';
            }
            warningBannerHtml = `
                <div class="alert ${alertClass} bg-opacity-10 border border-opacity-20 d-flex align-items-center gap-2 mb-3 py-2 rounded-3 w-100">
                    <i class="bi ${iconClass}"></i>
                    <div class="fw-bold small">${latestCoffeeChemistryData.recipe_validation}</div>
                </div>
            `;
        }
        if (currentLabMode === 'SODA' && latestSodaChemistryData && latestSodaChemistryData.recipe_validation && latestSodaChemistryData.recipe_validation !== 'Pass') {
            let alertClass = 'alert-warning border-warning text-warning';
            let iconClass = 'bi-exclamation-triangle-fill';
            if (latestSodaChemistryData.recipe_validation.toLowerCase().includes('fail')) {
                alertClass = 'alert-danger border-danger text-danger';
                iconClass = 'bi-x-circle-fill';
            }
            warningBannerHtml = `
                <div class="alert ${alertClass} bg-opacity-10 border border-opacity-20 d-flex align-items-center gap-2 mb-3 py-2 rounded-3 w-100">
                    <i class="bi ${iconClass}"></i>
                    <div class="fw-bold small">${latestSodaChemistryData.recipe_validation}</div>
                </div>
            `;
        }
        if (currentLabMode === 'SLUSHIE' && latestCryoChemistryData && latestCryoChemistryData.recipe_validation && latestCryoChemistryData.recipe_validation !== 'Pass') {
            const isSugarDensityFailure = latestCryoChemistryData.recipe_validation.toLowerCase().includes('sugar density');
            if (isMixSealed || !isSugarDensityFailure) {
                let alertClass = 'alert-warning border-warning text-warning';
                let iconClass = 'bi-exclamation-triangle-fill';
                if (latestCryoChemistryData.recipe_validation.toLowerCase().includes('fail')) {
                    alertClass = 'alert-danger border-danger text-danger';
                    iconClass = 'bi-x-circle-fill';
                }
                warningBannerHtml = `
                    <div class="alert ${alertClass} bg-opacity-10 border border-opacity-20 d-flex align-items-center gap-2 mb-3 py-2 rounded-3 w-100">
                        <i class="bi ${iconClass}"></i>
                        <div class="fw-bold small">${latestCryoChemistryData.recipe_validation}</div>
                    </div>
                `;
            }
        }

        let html = warningBannerHtml + '<div class="row g-2 mb-3">';
        let hiddenInputs = '';

        // 💧 Inject virtual Water card for Slushie mode to the left of the base ingredient
        if (currentLabMode === 'SLUSHIE' && !hasRtdBase) {
            finalWater = Math.max(0, bottleScale * 946.0 - totalSyrup);
            let fillerName = "Water";
            let isOverflow = false;
            
            if (allCryoAligned && latestCryoChemistryData && latestCryoChemistryData.ingredients && latestCryoChemistryData.ingredients.filler) {
                finalWater = latestCryoChemistryData.ingredients.filler.volume_ml;
                fillerName = latestCryoChemistryData.ingredients.filler.name;
            }
            if (allCryoAligned && latestCryoChemistryData && latestCryoChemistryData.recipe_validation) {
                isOverflow = latestCryoChemistryData.recipe_validation.toLowerCase().includes('capacity') || latestCryoChemistryData.recipe_validation.toLowerCase().includes('overflow');
            } else {
                isOverflow = totalSyrup > (bottleScale * 946.0);
            }
            
            const warningHtml = isOverflow ? `
                <div class="badge bg-danger text-white px-2 py-1 mt-2" style="font-size: 0.55rem;">
                    <i class="bi bi-exclamation-triangle-fill"></i> OVERFLOW / CAUTION
                </div>
            ` : '';

            let targetLabel = '';
            if (Math.abs(bottleScale - 0.5) < 0.01) targetLabel = '16oz';
            else if (Math.abs(bottleScale - 1.0) < 0.01) targetLabel = '32oz';
            else if (Math.abs(bottleScale - 1.5) < 0.01) targetLabel = '48oz';
            else if (Math.abs(bottleScale - 2.0) < 0.01) targetLabel = '64oz';

            html += `
                <div class="col-auto animate-fade-in">
                    <div class="glass-card p-2 text-center px-4 border-info border-opacity-20 ${isOverflow ? 'border-danger' : ''}" style="min-width: 150px; position: relative;">
                        <span class="readout-label d-block mb-1" style="font-size: 0.55rem;">VOLUME FILLER</span>
                        <div class="fw-bold mb-1" style="font-size: 0.9rem;">${fillerName} <i class="bi bi-droplets text-info ms-1"></i></div>
                        <div class="text-gradient-lab fw-black mb-2" style="font-size: 0.75rem;">${finalWater.toFixed(1)}ml / ${formatImperialVolume(finalWater)}</div>
                        <div class="mt-1 pt-1 border-top border-white border-opacity-10">
                            <div class="d-flex flex-column gap-1" style="font-size: 0.55rem; color: var(--text-dim);">
                                <div class="d-flex justify-content-between"><span>ROLE</span> <span class="text-info fw-bold">FILL LINE</span></div>
                                <div class="d-flex justify-content-between"><span>TARGET</span> <span>${targetLabel}</span></div>
                            </div>
                            ${warningHtml}
                        </div>
                    </div>
                </div>
            `;
        }
        
        // 💧 Inject virtual Carbonated Water card for Soda mode to the left of the base ingredient
        if (currentLabMode === 'SODA' && !hasRtdBase) {
            let finalWater = 840.0 * bottleScale;
            let isOverflow = false;
            if (allSodaAligned && latestSodaChemistryData && latestSodaChemistryData.ingredients && latestSodaChemistryData.ingredients.carbonated_water) {
                finalWater = latestSodaChemistryData.ingredients.carbonated_water.volume_ml;
            }
            if (allSodaAligned && latestSodaChemistryData && latestSodaChemistryData.recipe_validation) {
                isOverflow = latestSodaChemistryData.recipe_validation.toLowerCase().includes('fail');
            } else {
                isOverflow = totalSyrup > (160.0 * bottleScale);
            }
            
            const warningHtml = isOverflow ? `
                <div class="badge bg-danger text-white px-2 py-1 mt-2" style="font-size: 0.55rem;">
                    <i class="bi bi-exclamation-triangle-fill"></i> OVERFLOW
                </div>
            ` : '';

            let targetLabel = '';
            if (Math.abs(bottleScale - 1.0) < 0.01) targetLabel = '1.0L';
            else if (Math.abs(bottleScale - 0.5) < 0.01) targetLabel = '0.5L';
            else if (Math.abs(bottleScale - 0.355) < 0.01) targetLabel = '12oz';

            html += `
                <div class="col-auto animate-fade-in">
                    <div class="glass-card p-2 text-center px-4 border-info border-opacity-20 ${isOverflow ? 'border-danger' : ''}" style="min-width: 150px; position: relative;">
                        <span class="readout-label d-block mb-1" style="font-size: 0.55rem;">VOLUME FILLER</span>
                        <div class="fw-bold mb-1" style="font-size: 0.9rem;">Carbonated Water <i class="bi bi-droplets text-info ms-1"></i></div>
                        <div class="text-gradient-lab fw-black mb-2" style="font-size: 0.75rem;">${finalWater.toFixed(0)}ml / ${formatImperialVolume(finalWater)}</div>
                        <div class="mt-1 pt-1 border-top border-white border-opacity-10">
                            <div class="d-flex flex-column gap-1" style="font-size: 0.55rem; color: var(--text-dim);">
                                <div class="d-flex justify-content-between"><span>ROLE</span> <span class="text-info fw-bold">CARBONATION</span></div>
                                <div class="d-flex justify-content-between"><span>TARGET</span> <span>${targetLabel}</span></div>
                            </div>
                            ${warningHtml}
                        </div>
                    </div>
                </div>
            `;
        }
        
        const roles = ['BASE', 'PAYLOAD', 'ACCENT', 'DEEP ACCENT', 'STABILIZER'];

        selectedIngredients.forEach((ing, index) => {
            const isLast = index === (selectedIngredients.length - 1);
            const isFull = selectedIngredients.length >= maxIngredients || isDone;
            
            let role;
            if (hasRtdBase && index === firstRtdIndex && currentLabMode !== 'COFFEE') {
                role = 'VOLUME FILLER';
            } else if (currentLabMode === 'COFFEE') {
                const ingType = (ing.type || ing.ingredient_type || '').toUpperCase();
                if (ingType === 'COFFEE_BEAN') {
                    role = 'COFFEE BASE';
                } else if (ingType === 'DAIRY') {
                    role = 'PAYLOAD';
                } else if (ingType === 'ADDITIVE') {
                    role = 'ACCENT';
                } else if (ingType === 'SODA_SYRUP') {
                    role = 'FINAL';
                } else {
                    role = 'FINAL';
                }
            } else {
                role = (isLast && isFull) ? 'FINAL' : (roles[index] || 'MODIFIER');
            }
            
            let amount = ing.amount;
            let balanceIndicator = '';
            
            if (ing.isAiBalanced) {
                balanceIndicator = '<i class="bi bi-cpu text-neural ms-1" title="Neural Balanced"></i>';
            }

            const isDry = ing.isDry === true || ing.isDry === 'true';
            const isDryCoffee = currentLabMode === 'COFFEE' && (ing.type || ing.ingredient_type || '').toUpperCase() === 'COFFEE_BEAN';
            const ingUnit = (isDry || isDryCoffee) ? 'g' : 'ml';

            let alignedItem = null;
            let sodaAligned = null;
            let cryoAligned = null;
            if (currentLabMode === 'SODA' && allSodaAligned && latestSodaChemistryData && latestSodaChemistryData.ingredients) {
                const list = latestSodaChemistryData.ingredients.modifiers || [];
                sodaAligned = list.find(m => m.id == ing.id);
            } else if (currentLabMode === 'SLUSHIE' && allCryoAligned && latestCryoChemistryData && latestCryoChemistryData.ingredients) {
                const list = latestCryoChemistryData.ingredients.modifiers || [];
                cryoAligned = list.find(m => m.id == ing.id);
            }

            let displayVolume;
            let dualLabel;
            let mainName = ing.name;
            let renameWarningHtml = '';

            if (currentLabMode === 'COFFEE') {
                alignedItem = getChemistryAlignedIngredient(ing, index);
                if (alignedItem) {
                    if (isDryCoffee) {
                        amount = coffeeAmountForIngredient(ing, index, coffeeSizeOz, coffeeBaseType);
                    } else {
                        // Convert fluid ounces back to ml
                        amount = alignedItem.volume_oz * 29.5735;
                    }
                    
                    let engineName = alignedItem.name.replace(/\s+\((Dominant|Accent)\)$/i, '');
                    if (engineName.toLowerCase() !== ing.name.toLowerCase() && !isDryCoffee && ing.type !== 'DAIRY') {
                        mainName = engineName;
                        renameWarningHtml = `
                            <div class="text-warning small mt-1 font-monospace" style="font-size: 0.65rem;">
                                <i class="bi bi-exclamation-triangle-fill"></i> ${ing.name} &rarr; ${engineName}
                            </div>
                        `;
                    }
                } else {
                    if (ing.isAiBalanced && ing.aiRatio !== undefined && ing.type !== 'COFFEE_BEAN' && ing.type !== 'DAIRY') {
                        amount = Math.round(coffeeAmountForIngredient(ing, index, coffeeSizeOz, coffeeBaseType) * ing.aiRatio);
                    } else {
                        amount = coffeeAmountForIngredient(ing, index, coffeeSizeOz, coffeeBaseType);
                    }
                    const isDryCoffee2 = ing.type === 'COFFEE_BEAN';
                    const maxVal = isDryCoffee2 ? 40.0 : (ing.type === 'DAIRY' ? 300.0 : 120.0);
                    if (amount > maxVal) {
                        amount = coffeeAmountForIngredient(ing, index, coffeeSizeOz, coffeeBaseType);
                    }
                }

                displayVolume = isDryCoffee ? (amount * bottleScale).toFixed(1) : (amount * (bottleScale || 1.0)).toFixed(0);

                if (alignedItem) {
                    if (isDryCoffee) {
                        if (coffeeBaseType === 'espresso') {
                            const shots = Math.round(parseFloat(amount || 0) / 18.0);
                            dualLabel = `${shots} shot${shots !== 1 ? 's' : ''} (${alignedItem.volume_oz.toFixed(2)}oz extraction)`;
                        } else {
                            dualLabel = `${alignedItem.volume_oz.toFixed(1)}oz (${parseFloat(amount).toFixed(1)}g)`;
                        }
                    } else if (alignedItem.is_corrected) {
                        const pri_ml = Math.round(alignedItem.primary_volume_oz * 29.5735);
                        const tex_ml = Math.round(alignedItem.texturizer_volume_oz * 29.5735);
                        dualLabel = `${pri_ml}ml (Primary Filler) & Heavy Cream: ${tex_ml}ml (Texture Anchor)`;
                    } else {
                        dualLabel = `${displayVolume}${ingUnit} / ${alignedItem.volume_oz}oz`;
                    }
                } else {
                    if (isDryCoffee) {
                        if (coffeeBaseType === 'espresso') {
                            const shots = Math.round(parseFloat(amount || 0) / 18.0);
                            dualLabel = `${shots} shot${shots !== 1 ? 's' : ''} (${(shots * 0.9).toFixed(2)}oz extraction)`;
                        } else {
                            const totalG = getTotalCoffeeBeansGrams();
                            const oz = totalG > 0 ? (amount * (coffeeBaseAmount / totalG)).toFixed(1) : coffeeBaseAmount;
                            dualLabel = `${oz}oz (${parseFloat(amount).toFixed(1)}g)`;
                        }
                    } else {
                        dualLabel = `${displayVolume}${ingUnit} / ${formatImperialVolume(displayVolume)}`;
                    }
                }
            } else if (sodaAligned) {
                amount = sodaAligned.volume_ml;
                role = sodaAligned.role;
                displayVolume = amount.toFixed(1);
                dualLabel = `${displayVolume}${ingUnit} / ${formatImperialVolume(displayVolume)} (${sodaAligned.percentage_of_syrup}% of budget)`;
            } else if (cryoAligned) {
                amount = cryoAligned.volume_ml;
                role = cryoAligned.role;
                displayVolume = amount.toFixed(1);
                dualLabel = `${displayVolume}${ingUnit} / ${formatImperialVolume(displayVolume)} (${cryoAligned.percentage_of_batch}% of batch)`;
            } else {
                if (hasRtdBase && index === firstRtdIndex) {
                    amount = rtdBaseAmount;
                } else if (isDry) {
                    if (!amount) {
                        amount = 15.0 * (bottleScale || 1.0);
                    } else {
                        amount = amount * (bottleScale || 1.0);
                    }
                } else if (!amount) {
                    const baseVolume = index === 0 ? 80.0 : (index === 1 ? 40.0 : 20.0);
                    amount = baseVolume * (bottleScale || 1.0) * expansionFactor;
                } else {
                    amount = amount * (bottleScale || 1.0) * expansionFactor;
                }
                if (currentLabMode === 'SLUSHIE' && hasRtdBase && index === firstRtdIndex) {
                    displayVolume = amount.toFixed(1);
                } else {
                    displayVolume = isDry ? amount.toFixed(1) : amount.toFixed(0);
                }

                if (isDry) {
                    dualLabel = `${displayVolume} g`;
                } else {
                    dualLabel = `${displayVolume}${ingUnit} / ${formatImperialVolume(displayVolume)}`;
                }
            }

            if ((currentLabMode === 'SLUSHIE' || currentLabMode === 'SODA') && !isDry) {
                totalSyrup += parseFloat(amount);
            }

            let sliderHtml = '';
            const coffeeBeans = selectedIngredients.filter(x => (x.type || x.ingredient_type || '').toUpperCase() === 'COFFEE_BEAN');
            if (currentLabMode === 'COFFEE' && (ing.type || ing.ingredient_type || '').toUpperCase() === 'COFFEE_BEAN' && coffeeBeans.length > 1) {
                const totalG = getTotalCoffeeBeansGrams();
                const curVal = parseFloat(amount || 0);
                const isEspresso = (coffeeBaseType === 'espresso');
                
                let displayVal = '';
                if (isEspresso) {
                    const shots = Math.round(curVal / 18.0);
                    displayVal = `${shots} shot${shots !== 1 ? 's' : ''}`;
                } else {
                    displayVal = `${Math.round(curVal)}g`;
                }

                sliderHtml = `
                    <div class="my-2 px-1 d-flex flex-column align-items-center gap-1">
                        <div class="d-flex align-items-center justify-content-center gap-2">
                            <button type="button" class="btn btn-xs btn-outline-warning px-2 py-0 border-white border-opacity-10 text-white font-monospace" onclick="adjustCoffeeBeanSplitButtons(${ing.id}, -1)">-</button>
                            <span class="text-white font-monospace small" style="min-width: 55px; display: inline-block;">${displayVal}</span>
                            <button type="button" class="btn btn-xs btn-outline-warning px-2 py-0 border-white border-opacity-10 text-white font-monospace" onclick="adjustCoffeeBeanSplitButtons(${ing.id}, 1)">+</button>
                        </div>
                        <div class="text-dim font-monospace mt-1" style="font-size: 0.55rem;">SPLIT: ${curVal.toFixed(1)}g / ${totalG.toFixed(1)}g</div>
                        <button type="button" class="btn btn-xs btn-outline-danger px-2 py-0.5 border-white border-opacity-10 mt-1" style="font-size: 0.55rem;" onclick="removeCoffeeBeanSplit(${ing.id})">
                            <i class="bi bi-trash"></i> Remove Split
                        </button>
                    </div>
                `;
            }
            
            const ingTypeForPrim = (ing.type || ing.ingredient_type || '').toUpperCase();
            const isFlavorModifier = ['SODA_SYRUP', 'ADDITIVE', 'OTHER'].includes(ingTypeForPrim) && !isDry;
            const isSodaPrim = currentLabMode === 'SODA' && isFlavorModifier && ing.isPrimary;
            const borderGlowClass = isSodaPrim ? 'border-warning' : (ing.isAiBalanced ? 'border-neural glow-neural' : '');
            const extraStyle = isSodaPrim ? 'box-shadow: 0 0 12px rgba(255, 193, 7, 0.35); border-color: rgba(255, 193, 7, 0.5) !important;' : '';

            let anchorTogglerHtml = '';
            if (currentLabMode === 'SODA' && isFlavorModifier) {
                if (ing.isPrimary) {
                    anchorTogglerHtml = `
                        <div class="mb-2">
                            <span class="badge bg-warning text-dark px-2 py-0.5 cursor-pointer" onclick="setPrimaryAnchor('${ing.id}')" style="font-size: 0.55rem;" title="Core featured flavor anchor">
                                <i class="bi bi-star-fill me-1"></i>PRIMARY ANCHOR
                            </span>
                        </div>
                    `;
                } else {
                    anchorTogglerHtml = `
                        <div class="mb-2">
                            <span class="badge border border-white border-opacity-25 text-dim px-2 py-0.5 cursor-pointer hover-lime" onclick="setPrimaryAnchor('${ing.id}')" style="font-size: 0.55rem;" title="Set as primary flavor anchor">
                                <i class="bi bi-star me-1"></i>SET ANCHOR
                            </span>
                        </div>
                    `;
                }
            }

            html += `
                <div class="col-auto animate-fade-in">
                    <div class="glass-card p-2 text-center px-4 ${borderGlowClass}" style="min-width: 150px; position: relative; ${extraStyle}">
                        <span class="readout-label d-block mb-1" style="font-size: 0.55rem;">${role}</span>
                        ${anchorTogglerHtml}
                        <div class="fw-bold mb-1" style="font-size: 0.9rem;">${mainName} ${balanceIndicator}</div>
                        ${renameWarningHtml}
                        <div class="text-gradient-lab fw-black mb-2" style="font-size: 0.75rem;">${dualLabel}</div>
                        ${sliderHtml}
                        
                        <!-- 🧪 Synthesized Profile Display -->
                        <div class="mt-1 pt-1 border-top border-white border-opacity-10">
                            <div class="d-flex flex-column gap-1" style="font-size: 0.55rem;">
                                ${['intensity', 'sweetness', 'acidity', 'bitterness', 'complexity'].map(attr => {
                                    const val = (ing.profile && ing.profile[attr] !== undefined) ? ing.profile[attr] : (ing[attr] || 0);
                                    const isSynthesized = ing.profile && ing.profile[attr] !== undefined;
                                    const isNeural = (engineMode === 'ai') || ing.isAiBalanced || isSynthesized;
                                    const color = isNeural ? 'var(--fizz-cyan)' : 'var(--text-dim)';
                                    return `
                                        <div class="d-flex justify-content-between align-items-center gap-2">
                                            <span style="color: ${color}; text-transform: uppercase;">${attr.slice(0, 3)}</span>
                                            <div class="flex-grow-1 bg-white bg-opacity-10" style="height: 2px;">
                                                <div style="width: ${(val/5)*100}%; height: 100%; background: ${color}; box-shadow: ${isNeural ? '0 0 5px var(--fizz-cyan)' : 'none'};"></div>
                                            </div>
                                            <span style="min-width: 8px; color: ${isNeural ? 'white' : 'var(--text-dim)'};">${val}</span>
                                        </div>
                                    `;
                                }).join('')}
                            </div>
                        </div>
                    </div>
                </div>
            `;

            // 🧊 Inject virtual Ice card right next to the coffee base for iced style
            const isLastCoffeeBean = isDryCoffee && (coffeeBeans.length > 0 && coffeeBeans[coffeeBeans.length - 1].id === ing.id);
            if (currentLabMode === 'COFFEE' && isLastCoffeeBean && coffeeStyle === 'iced') {
                const iceOz = getIceAmountOz(coffeeSizeOz);
                const iceMl = Math.round(iceOz * 29.5735);
                html += `
                    <div class="col-auto">
                        <div class="glass-card p-2 text-center px-4 border-info border-opacity-20" style="min-width: 150px; position: relative;">
                            <span class="readout-label d-block mb-1" style="font-size: 0.55rem;">BASE MODIFIER</span>
                            <div class="fw-bold mb-1" style="font-size: 0.9rem;">Ice <i class="bi bi-snow text-info ms-1"></i></div>
                            <div class="text-gradient-lab fw-black mb-2" style="font-size: 0.75rem;">${iceOz}oz</div>
                            <div class="mt-1 pt-1 border-top border-white border-opacity-10">
                                <div class="d-flex flex-column gap-1" style="font-size: 0.55rem; color: var(--text-dim);">
                                    <div class="d-flex justify-content-between"><span>TEMP</span> <span class="text-info fw-bold">COLD</span></div>
                                    <div class="d-flex justify-content-between"><span>VOLUME</span> <span>~${iceMl}ml</span></div>
                                </div>
                            </div>
                        </div>
                    </div>
                `;
            }

            // 💧 Inject virtual Hot Water card right next to the coffee base for hot espresso in water mode
            if (currentLabMode === 'COFFEE' && isLastCoffeeBean && coffeeStyle === 'hot' && coffeeBaseType === 'espresso' && coffeeEspressoHotMode === 'water') {
                const hotWaterOz = (coffeeBaseAmount * 0.9).toFixed(1);
                const hotWaterMl = Math.round(hotWaterOz * 29.5735);
                html += `
                    <div class="col-auto">
                        <div class="glass-card p-2 text-center px-4 border-info border-opacity-20" style="min-width: 150px; position: relative;">
                            <span class="readout-label d-block mb-1" style="font-size: 0.55rem;">BASE MODIFIER</span>
                            <div class="fw-bold mb-1" style="font-size: 0.9rem;">Hot Water <i class="bi bi-droplets text-info ms-1"></i></div>
                            <div class="text-gradient-lab fw-black mb-2" style="font-size: 0.75rem;">${hotWaterOz}oz</div>
                            <div class="mt-1 pt-1 border-top border-white border-opacity-10">
                                <div class="d-flex flex-column gap-1" style="font-size: 0.55rem; color: var(--text-dim);">
                                    <div class="d-flex justify-content-between"><span>TEMP</span> <span class="text-danger fw-bold">HOT</span></div>
                                    <div class="d-flex justify-content-between"><span>VOLUME</span> <span>~${hotWaterMl}ml</span></div>
                                </div>
                            </div>
                        </div>
                    </div>
                `;
            }

            if (ing.id !== 'virtual_water') {
                hiddenInputs += `<input type="hidden" name="ingredient_${ing.id}" value="${ing.id}">`;
                hiddenInputs += `<input type="hidden" name="amount_${ing.id}" value="${amount}">`;
                
                // 🧪 Inject Synthesized Profile Overrides into the form
                if (ing.profile) {
                    hiddenInputs += `<input type="hidden" name="intensity_${ing.id}" value="${ing.profile.intensity}">`;
                    hiddenInputs += `<input type="hidden" name="sweetness_${ing.id}" value="${ing.profile.sweetness}">`;
                    hiddenInputs += `<input type="hidden" name="acidity_${ing.id}" value="${ing.profile.acidity}">`;
                    hiddenInputs += `<input type="hidden" name="bitterness_${ing.id}" value="${ing.profile.bitterness}">`;
                }
            }
        });
        
        html += '</div>';


        
        let hasZeroValueMismatch = false;
        if (currentLabMode === 'SLUSHIE' && latestCryoChemistryData) {
            // Check filler (Water)
            if (latestCryoChemistryData.ingredients && latestCryoChemistryData.ingredients.filler) {
                const backendFillerVol = latestCryoChemistryData.ingredients.filler.volume_ml;
                if (backendFillerVol > 0 && finalWater <= 0.05) {
                    hasZeroValueMismatch = true;
                }
            }
            // Check modifiers
            const backendModifiers = (latestCryoChemistryData.ingredients && latestCryoChemistryData.ingredients.modifiers) || [];
            selectedIngredients.forEach((ing, index) => {
                const type = (ing.type || ing.ingredient_type || '').toUpperCase();
                if (type !== 'COFFEE_BEAN' && type !== 'DAIRY' && ing.id !== 'virtual_water') {
                    const matched = backendModifiers.find(m => m.id == ing.id);
                    if (matched) {
                        const backendVol = matched.volume_ml;
                        let renderedVol = ing.amount;
                        if (allCryoAligned) {
                            renderedVol = matched.volume_ml;
                        } else {
                            if (hasRtdBase && index === firstRtdIndex) {
                                renderedVol = rtdBaseAmount;
                            } else if (ing.isDry === true || ing.isDry === 'true') {
                                renderedVol = (ing.amount || 15.0) * bottleScale;
                            } else {
                                const baseVolume = index === 0 ? 80.0 : (index === 1 ? 40.0 : 20.0);
                                renderedVol = (ing.amount || baseVolume) * bottleScale * expansionFactor;
                            }
                        }
                        if (backendVol > 0 && renderedVol <= 0.05) {
                            hasZeroValueMismatch = true;
                        }
                    }
                }
            });
        }
        if (currentLabMode === 'SODA' && latestSodaChemistryData) {
            if (latestSodaChemistryData.ingredients && latestSodaChemistryData.ingredients.carbonated_water) {
                const backendFillerVol = latestSodaChemistryData.ingredients.carbonated_water.volume_ml;
                const waterVol = (allSodaAligned && latestSodaChemistryData.ingredients.carbonated_water) ? latestSodaChemistryData.ingredients.carbonated_water.volume_ml : (840.0 * bottleScale);
                if (backendFillerVol > 0 && waterVol <= 0.05) {
                    hasZeroValueMismatch = true;
                }
            }
            const backendModifiers = (latestSodaChemistryData.ingredients && latestSodaChemistryData.ingredients.modifiers) || [];
            selectedIngredients.forEach((ing, index) => {
                const type = (ing.type || ing.ingredient_type || '').toUpperCase();
                if (type !== 'COFFEE_BEAN' && type !== 'DAIRY' && ing.id !== 'virtual_water') {
                    const matched = backendModifiers.find(m => m.id == ing.id);
                    if (matched) {
                        const backendVol = matched.volume_ml;
                        let renderedVol = ing.amount;
                        if (allSodaAligned) {
                            renderedVol = matched.volume_ml;
                        } else {
                            if (ing.isDry === true || ing.isDry === 'true') {
                                renderedVol = (ing.amount || 15.0) * bottleScale;
                            } else {
                                const baseVolume = index === 0 ? 80.0 : (index === 1 ? 40.0 : 20.0);
                                renderedVol = (ing.amount || baseVolume) * bottleScale * expansionFactor;
                            }
                        }
                        if (backendVol > 0 && renderedVol <= 0.05) {
                            hasZeroValueMismatch = true;
                        }
                    }
                }
            });
        }

        if ((isDone || selectedIngredients.length >= maxIngredients) && !hasZeroValueMismatch) {
            html += `<div class="alert bg-success bg-opacity-10 border border-success border-opacity-20 text-success small py-2">
                        <i class="bi bi-check2-circle"></i> Formulation complete. Synthesis ready for indexing.
                    </div>`;
            html += hiddenInputs;
            submitArea.style.display = 'block';
        } else {
            submitArea.style.display = 'none';
        }
        
        // Blended Bean Dropdown population
        const dropdownContainer = document.getElementById('mixBeanDropdownContainer');
        const dropdownMenu = document.getElementById('mixBeanDropdownMenu');
        if (dropdownContainer && dropdownMenu) {
            const coffeeBeansInMix = selectedIngredients.filter(x => (x.type || x.ingredient_type || '').toUpperCase() === 'COFFEE_BEAN');
            const isEspressoBase = (coffeeBaseType === 'espresso');
            const canSplit = !isEspressoBase || (coffeeBaseAmount >= 2);
            if (currentLabMode === 'COFFEE' && coffeeBeansInMix.length > 0 && !isMixSealed && canSplit) {
                dropdownContainer.style.setProperty('display', 'inline-block', 'important');
                
                // Get all COFFEE_BEAN buttons from availableIngredients
                const tempDiv = document.createElement('div');
                tempDiv.innerHTML = allIngredientsHtml;
                const allCoffeeButtons = Array.from(tempDiv.querySelectorAll('.select-ingredient-btn'))
                    .filter(btn => btn.getAttribute('data-type') === 'COFFEE_BEAN');
                
                // Filter out already selected beans
                const selectedIds = selectedIngredients.map(x => x.id.toString());
                const availableToBlend = allCoffeeButtons.filter(btn => !selectedIds.includes(btn.getAttribute('data-id')));
                
                if (availableToBlend.length > 0) {
                    dropdownMenu.innerHTML = availableToBlend.map(btn => {
                        const id = btn.getAttribute('data-id');
                        const name = btn.getAttribute('data-name');
                        const intensity = btn.getAttribute('data-intensity');
                        const category = btn.getAttribute('data-category');
                        const profile = btn.getAttribute('data-profile') || '';
                        const sweetness = btn.getAttribute('data-sweetness') || 0;
                        const acidity = btn.getAttribute('data-acidity') || 0;
                        const bitterness = btn.getAttribute('data-bitterness') || 0;
                        const complexity = btn.getAttribute('data-complexity') || 0;
                        const type = btn.getAttribute('data-type');
                        const isReadyToDrink = btn.getAttribute('data-is-ready-to-drink') === 'true';
                        const isDry = btn.getAttribute('data-is-dry') === 'true';
                        const roastLevel = btn.getAttribute('data-roast-level') || '';
                        const flavorNotes = btn.getAttribute('data-flavor-notes') || '';
                        const isDecaf = btn.getAttribute('data-is-decaf') === 'true';
                        
                        const profileEscaped = profile.replace(/'/g, "\\'");
                        const nameEscaped = name.replace(/'/g, "\\'");
                        
                        return `
                            <li>
                                <a class="dropdown-item text-white hover-lime" href="#" onclick="event.preventDefault(); selectIngredient(${id}, '${nameEscaped}', ${intensity}, '${category}', '${profileEscaped}', false, null, ${sweetness}, ${acidity}, ${bitterness}, ${complexity}, '${type}', ${isReadyToDrink}, ${isDry}, '${roastLevel}', '${flavorNotes}', ${isDecaf})">
                                    ${name}
                                </a>
                            </li>
                        `;
                    }).join('');
                } else {
                    dropdownMenu.innerHTML = '<li><span class="dropdown-item-text text-dim small">No other coffee beans in registry</span></li>';
                }
            } else {
                dropdownContainer.style.setProperty('display', 'none', 'important');
            }
        }
        
        list.innerHTML = html;
    }

    function fetchSuggestName() {
        const btn = document.getElementById('suggestBtn');
        btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';
        const ids = selectedIngredients.map(i => i.id);
        fetch('/api/generate-name/', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ingredient_ids: ids, drink_type: currentLabMode})
        })
        .then(r => r.json())
        .then(data => {
            document.getElementById('recipeNameField').value = data.name;
            btn.innerHTML = '<i class="bi bi-magic"></i>';
        });
    }

    function interceptAndSave() {
        let calculatedSizeOz = null;
        if (currentLabMode === 'COFFEE') {
            calculatedSizeOz = coffeeSizeOz;
        } else if (currentLabMode === 'SODA') {
            if (bottleScale === 1.0) calculatedSizeOz = 33.8;
            else if (bottleScale === 0.5) calculatedSizeOz = 16.9;
            else if (bottleScale === 0.355) calculatedSizeOz = 12.0;
        } else if (currentLabMode === 'SLUSHIE') {
            calculatedSizeOz = bottleScale * 32.0;
        }

        const drinkSizeOzField = document.getElementById('drinkSizeOzField');
        if (drinkSizeOzField) {
            drinkSizeOzField.value = calculatedSizeOz;
        }

        const hasRtdBase = selectedIngredients.some(ing => ing.isReadyToDrink);
        const firstRtdIndex = selectedIngredients.findIndex(ing => ing.isReadyToDrink);

        let initialTotal = 0;
        const limit = (160 * (bottleScale || 1.0));
        
        if (!hasRtdBase) {
            selectedIngredients.forEach((ing, index) => {
                let amt = ing.amount;
                const isDry = ing.isDry === true || ing.isDry === 'true' || (currentLabMode === 'COFFEE' && ing.type === 'COFFEE_BEAN');
                if (!amt) {
                    const baseVol = isDry ? 18.0 : (index === 0 ? 80.0 : (index === 1 ? 40.0 : 20.0));
                    amt = baseVol * (bottleScale || 1.0);
                } else if (currentLabMode !== 'COFFEE') {
                    amt = amt * (bottleScale || 1.0);
                }
                if (!isDry) {
                    initialTotal += parseFloat(amt);
                }
            });
        }

        let expansionFactor = 1.0;
        if (!hasRtdBase && initialTotal < limit && initialTotal > 0 && currentLabMode !== 'COFFEE') {
            expansionFactor = limit / initialTotal;
        }

        let rtdBaseAmount = 0;
        if (hasRtdBase && currentLabMode !== 'COFFEE') {
            const bottleCapacity = (currentLabMode === 'SODA') ? (bottleScale * 1000) : (bottleScale * 946.35);
            let nonFillerTotal = 0;
            selectedIngredients.forEach((ing, index) => {
                if (index !== firstRtdIndex) {
                    let amt = ing.amount;
                    const isDry = ing.isDry === true || ing.isDry === 'true';
                    if (!amt) {
                        const baseVolume = isDry ? 18.0 : (index === 0 ? 80.0 : (index === 1 ? 40.0 : 20.0));
                        amt = baseVolume * (bottleScale || 1.0);
                    } else {
                        amt = amt * (bottleScale || 1.0);
                    }
                    if (!isDry) {
                        nonFillerTotal += parseFloat(amt);
                    }
                }
            });
            rtdBaseAmount = Math.max(0, bottleCapacity - nonFillerTotal);
        }

        const data = {
            drink_type: currentLabMode,
            coffee_style: coffeeStyle,
            coffee_base_type: coffeeBaseType,
            drink_size_oz: calculatedSizeOz,
            ingredients: selectedIngredients
                .filter(ing => ing.id !== 'virtual_water')
                .map((ing) => {
                    const idx = selectedIngredients.indexOf(ing);
                    let amount = ing.amount;
                    const isDry = ing.isDry === true || ing.isDry === 'true';
                    const isDryCoffee = currentLabMode === 'COFFEE' && ing.type === 'COFFEE_BEAN';
                    
                    let alignedItem = null;
                    if (currentLabMode === 'COFFEE') {
                        alignedItem = getChemistryAlignedIngredient(ing, idx);
                    }

                    if (currentLabMode === 'COFFEE') {
                        if (alignedItem) {
                            if (isDryCoffee) {
                                amount = coffeeAmountForIngredient(ing, idx, coffeeSizeOz, coffeeBaseType);
                            } else {
                                amount = alignedItem.volume_oz * 29.5735;
                            }
                        } else {
                            if (ing.isAiBalanced && ing.aiRatio !== undefined && ing.type !== 'COFFEE_BEAN' && ing.type !== 'DAIRY') {
                                amount = Math.round(coffeeAmountForIngredient(ing, idx, coffeeSizeOz, coffeeBaseType) * ing.aiRatio);
                            } else {
                                amount = coffeeAmountForIngredient(ing, idx, coffeeSizeOz, coffeeBaseType);
                            }
                            const maxVal = isDryCoffee ? 40.0 : (ing.type === 'DAIRY' ? 300.0 : 120.0);
                            if (amount > maxVal) amount = coffeeAmountForIngredient(ing, idx, coffeeSizeOz, coffeeBaseType);
                        }
                    } else if (hasRtdBase && idx === firstRtdIndex) {
                        amount = rtdBaseAmount;
                    } else if (isDry) {
                        if (!amount) {
                            amount = 15.0 * (bottleScale || 1.0);
                        } else {
                            amount = amount * (bottleScale || 1.0);
                        }
                    } else if (!amount) {
                        const baseVolume = idx === 0 ? 80.0 : (idx === 1 ? 40.0 : 20.0);
                        amount = baseVolume * bottleScale * expansionFactor;
                    } else {
                        amount = amount * bottleScale * expansionFactor;
                    }
                    
                    return {
                        id: parseInt(ing.id),
                        amount: amount,
                        profile: ing.profile || null
                    };
                })
        };

        const saveBtn = document.getElementById('saveMixBtn');
        saveBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span> ARCHIVING...';
        saveBtn.disabled = true;
        
        // 🧪 Lab Data Projection: Inject hidden inputs into mixerForm before submission
        const mixerForm = document.getElementById('mixerForm');
        
        // Clear any existing dynamic inputs to prevent duplicates
        const oldDynamic = mixerForm.querySelectorAll('.dynamic-mix-input');
        oldDynamic.forEach(el => el.remove());
 
        selectedIngredients.forEach((ing, idx) => {
            if (ing.id === 'virtual_water') {
                return;
            }
            let amount = ing.amount;
            const isDry = ing.isDry === true || ing.isDry === 'true';
            const isDryCoffee = currentLabMode === 'COFFEE' && ing.type === 'COFFEE_BEAN';
            
            let alignedItem = null;
            if (currentLabMode === 'COFFEE') {
                alignedItem = getChemistryAlignedIngredient(ing, idx);
            }

            if (currentLabMode === 'COFFEE') {
                if (alignedItem) {
                    if (isDryCoffee) {
                        amount = coffeeAmountForIngredient(ing, idx, coffeeSizeOz, coffeeBaseType);
                    } else {
                        amount = alignedItem.volume_oz * 29.5735;
                    }
                } else {
                    if (ing.isAiBalanced && ing.aiRatio !== undefined && ing.type !== 'COFFEE_BEAN' && ing.type !== 'DAIRY') {
                        amount = Math.round(coffeeAmountForIngredient(ing, idx, coffeeSizeOz, coffeeBaseType) * ing.aiRatio);
                    } else {
                        amount = coffeeAmountForIngredient(ing, idx, coffeeSizeOz, coffeeBaseType);
                    }
                    const maxVal = isDryCoffee ? 40.0 : (ing.type === 'DAIRY' ? 300.0 : 120.0);
                    if (amount > maxVal) amount = coffeeAmountForIngredient(ing, idx, coffeeSizeOz, coffeeBaseType);
                }
            } else if (hasRtdBase && idx === firstRtdIndex) {
                amount = rtdBaseAmount;
            } else if (isDry) {
                if (!amount) {
                    amount = 15.0 * (bottleScale || 1.0);
                } else {
                    amount = amount * (bottleScale || 1.0);
                }
            } else if (!amount) {
                const baseVolume = idx === 0 ? 80.0 : (idx === 1 ? 40.0 : 20.0);
                amount = baseVolume * bottleScale * expansionFactor;
            } else {
                amount = amount * bottleScale * expansionFactor;
            }
            
            // Create inputs matching views.create_recipe expectations
            const amountInput = document.createElement('input');
            amountInput.type = 'hidden';
            amountInput.name = `amount_${ing.id}`;
            amountInput.value = amount;
            amountInput.className = 'dynamic-mix-input';
            mixerForm.appendChild(amountInput);

            if (currentLabMode === 'SODA') {
                const primaryInput = document.createElement('input');
                primaryInput.type = 'hidden';
                primaryInput.name = `is_primary_${ing.id}`;
                primaryInput.value = ing.isPrimary ? 'true' : 'false';
                primaryInput.className = 'dynamic-mix-input';
                mixerForm.appendChild(primaryInput);
            }
 
            const notesInput = document.createElement('input');
            notesInput.type = 'hidden';
            notesInput.name = `notes_${ing.id}`;
            const styleLabel = { hot: 'Hot', iced: 'Iced', espresso_shot: 'Espresso Shot' }[coffeeStyle] || coffeeStyle;
            
            let scaleLabel = '';
            if (currentLabMode === 'SODA') {
                if (bottleScale === 1.0) scaleLabel = '1.0L Bottle';
                else if (bottleScale === 0.5) scaleLabel = '0.5L Bottle';
                else if (bottleScale === 0.355) scaleLabel = '12oz Glass';
            } else if (currentLabMode === 'SLUSHIE') {
                scaleLabel = (bottleScale * 32.0).toFixed(0) + 'oz Batch';
            }
            
            notesInput.value = currentLabMode === 'COFFEE'
                ? `Automatic laboratory synthesis — ${styleLabel}, ${coffeeSizeOz}oz, ${coffeeBaseType === 'espresso' ? 'Espresso base' : 'Standard Brew base'}`
                : `Automatic laboratory synthesis (${currentLabMode}) at ${scaleLabel}`;
            notesInput.className = 'dynamic-mix-input';
            mixerForm.appendChild(notesInput);
        });

        fetch('/api/history/save/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': window.CSRF_TOKEN },
            body: JSON.stringify(data)
        })
        .then(r => r.json())
        .then(res => {
            if (res.status === 'saved') {
                mixerForm.submit();
            } else {
                alert('Archive failure: ' + (res.error || 'Unknown error'));
                saveBtn.innerHTML = '<i class="bi bi-journal-plus me-2"></i> ARCHIVE SYNTHESIS';
                saveBtn.disabled = false;
            }
        })
        .catch(err => {
            console.error('Laboratory Archival Exception:', err);
            mixerForm.submit(); // Submit anyway on network error to allow recovery via view logic
        });
    }

