let currentScale = 1.0;
let currentSweetnessStyle = 'AUTO';

function setSodaSweetness(style) {
    currentSweetnessStyle = style;
    document.getElementById('sweetnessCrisp')?.classList.remove('active-lab-mode');
    document.getElementById('sweetnessCraft')?.classList.remove('active-lab-mode');
    document.getElementById('sweetnessFountain')?.classList.remove('active-lab-mode');
    
    if (style === 'CRISP') document.getElementById('sweetnessCrisp')?.classList.add('active-lab-mode');
    if (style === 'CRAFT') document.getElementById('sweetnessCraft')?.classList.add('active-lab-mode');
    if (style === 'FOUNTAIN') document.getElementById('sweetnessFountain')?.classList.add('active-lab-mode');
    
    fetchSodaChemistry();
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

    let savedSizeOz = parseFloat(window.RECIPE_DRINK_SIZE_OZ) || (window.RECIPE_DRINK_TYPE === 'CRYO' || window.RECIPE_DRINK_TYPE === 'SLUSHIE' ? 32.0 : 33.8);
    let drinkType = window.RECIPE_DRINK_TYPE;
    if (drinkType === 'SLUSHIE') drinkType = 'CRYO';

    // Coffee-specific state initialization
    let coffeeStyle = window.RECIPE_COFFEE_STYLE;
    let coffeeSizeOz = parseFloat(window.RECIPE_DRINK_SIZE_OZ || '12');
    let coffeeBaseType = window.RECIPE_COFFEE_BASE_TYPE;
    let coffeeBaseAmount = 2;
    let coffeeEspressoHotMode = 'shots'; // Forced to shots, Americano mode removed

    function setEspressoHotMode(mode) {
        coffeeEspressoHotMode = mode;
        localStorage.setItem('coffee_espresso_hot_mode', mode);
        const waterBtn = document.getElementById('hotModeWater');
        const shotsBtn = document.getElementById('hotModeShots');
        if (waterBtn) waterBtn.classList.toggle('active-lab-mode', mode === 'water');
        if (shotsBtn) shotsBtn.classList.toggle('active-lab-mode', mode === 'shots');
        
        recalculateCoffeeBaseAmount();
        updateAmounts();
    }

    function updateEspressoHotModeContainer() {
        const showHotEspressoAdj = (drinkType === 'COFFEE' && coffeeStyle === 'hot' && coffeeBaseType === 'espresso');
        const adjContainer = document.getElementById('espressoHotModeContainer');
        if (adjContainer) adjContainer.style.display = showHotEspressoAdj ? 'block' : 'none';
        
        // Sync active class on hot/water buttons
        const waterBtn = document.getElementById('hotModeWater');
        const shotsBtn = document.getElementById('hotModeShots');
        if (waterBtn) waterBtn.classList.toggle('active-lab-mode', coffeeEspressoHotMode === 'water');
        if (shotsBtn) shotsBtn.classList.toggle('active-lab-mode', coffeeEspressoHotMode === 'shots');
    }

    let latestCoffeeChemistryData = null;
    const savedCoffeeStyle = "window.RECIPE_COFFEE_STYLE";
    const savedCoffeeBaseType = "window.RECIPE_COFFEE_BASE_TYPE";

    function setCoffeeStyle(style) {
        coffeeStyle = style;
        
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
        if (sizeBtns) {
            if (shotMode) {
                sizeBtns.innerHTML = `
                    <button type="button" class="btn btn-sm btn-glass-toggle py-2 fs-6" id="size1oz" onclick="setCoffeeSize(1)">1 Shot</button>
                    <button type="button" class="btn btn-sm btn-glass-toggle py-2 fs-6" id="size2oz" onclick="setCoffeeSize(2)">2 Shots</button>
                    <button type="button" class="btn btn-sm btn-glass-toggle py-2 fs-6" id="size3oz" onclick="setCoffeeSize(3)">3 Shots</button>
                    <button type="button" class="btn btn-sm btn-glass-toggle py-2 fs-6" id="size4oz" onclick="setCoffeeSize(4)">4 Shots</button>
                `;
                // Force coffee base type to espresso for shots
                coffeeBaseType = 'espresso';
                const baseEsp = document.getElementById('baseEspresso');
                if (baseEsp) baseEsp.classList.add('active-lab-mode');
                const baseStd = document.getElementById('baseStandardBrew');
                if (baseStd) baseStd.classList.remove('active-lab-mode');
                
                const prev = coffeeSizeOz;
                const defaultSize = [1,2,3,4].includes(prev) ? prev : 2;
                setCoffeeSize(defaultSize);
            } else {
                const prev = coffeeSizeOz;
                const defaultSize = [8,12,16,20].includes(prev) ? prev : 12;
                sizeBtns.innerHTML = `
                    <button type="button" class="btn btn-sm btn-glass-toggle py-2 fs-6" id="size8oz"  onclick="setCoffeeSize(8)">8oz</button>
                    <button type="button" class="btn btn-sm btn-glass-toggle py-2 fs-6" id="size12oz" onclick="setCoffeeSize(12)">12oz</button>
                    <button type="button" class="btn btn-sm btn-glass-toggle py-2 fs-6" id="size16oz" onclick="setCoffeeSize(16)">16oz</button>
                    <button type="button" class="btn btn-sm btn-glass-toggle py-2 fs-6" id="size20oz" onclick="setCoffeeSize(20)">20oz</button>
                `;
                setCoffeeSize(defaultSize);
            }
        }

        // Show/hide Coffee Base Type selector based on style (shots are always espresso)
        const baseLabel = document.getElementById('coffeeBaseLabel');
        const baseBtns = document.getElementById('coffeeBaseBtns');
        if (baseLabel) baseLabel.style.display = shotMode ? 'none' : '';
        if (baseBtns) baseBtns.style.display = shotMode ? 'none' : '';

        recalculateCoffeeBaseAmount();
        updateEspressoHotModeContainer();
        updateAmounts();
    }

    function setCoffeeSize(oz) {
        coffeeSizeOz = parseFloat(oz);
        
        // Mark the active button
        const sizeContainer = document.getElementById('coffeeSizeBtns');
        if (sizeContainer) {
            sizeContainer.querySelectorAll('button').forEach(btn => {
                btn.classList.remove('active-lab-mode');
            });
            sizeContainer.querySelectorAll('button').forEach(btn => {
                const match = btn.getAttribute('onclick');
                if (match && match.includes('(' + oz + ')')) {
                    btn.classList.add('active-lab-mode');
                }
            });
        }
        
        recalculateCoffeeBaseAmount();
        updateEspressoHotModeContainer();
        updateAmounts();
    }

    function setCoffeeBaseType(type) {
        coffeeBaseType = type;
        const baseEsp = document.getElementById('baseEspresso');
        if (baseEsp) baseEsp.classList.toggle('active-lab-mode', type === 'espresso');
        const baseStd = document.getElementById('baseStandardBrew');
        if (baseStd) baseStd.classList.toggle('active-lab-mode', type === 'standard_brew');

        recalculateCoffeeBaseAmount();
        updateEspressoHotModeContainer();
        updateAmounts();
    }

    function getIceAmountOz(sizeOz) {
        return sizeOz * 0.40;
    }

    function recalculateCoffeeBaseAmount() {
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
    }

    function setBottleScale(targetScale, btnId) {
        let savedScale = 1.0;
        if (drinkType === 'SODA') {
            if (savedSizeOz === 12.0) savedScale = 0.355;
            else if (savedSizeOz === 16.9) savedScale = 0.5;
            else savedScale = 1.0;
        } else if (drinkType === 'CRYO') {
            savedScale = savedSizeOz / 32.0;
        }

        currentScale = targetScale / savedScale;
        
        document.querySelectorAll('.btn-glass-toggle').forEach(btn => {
            btn.classList.remove('active-lab-mode');
        });
        const activeBtn = document.getElementById(btnId);
        if (activeBtn) activeBtn.classList.add('active-lab-mode');
        
        updateAmounts();
    }

    function updateAmounts() {
        const amountDisplays = Array.from(document.querySelectorAll('.amount-display'));
        const hasRtdBase = amountDisplays.some(el => el.getAttribute('data-is-ready-to-drink') === 'true');
        const firstRtdIndex = amountDisplays.findIndex(el => el.getAttribute('data-is-ready-to-drink') === 'true');

        let savedScale = 1.0;
        if (drinkType === 'SODA') {
            if (savedSizeOz === 12.0) savedScale = 0.355;
            else if (savedSizeOz === 16.9) savedScale = 0.5;
            else savedScale = 1.0;
        } else if (drinkType === 'CRYO') {
            savedScale = savedSizeOz / 32.0;
        }
        const activeScale = currentScale * savedScale;
        const bottleCapacity = (drinkType === 'SODA') ? (activeScale * 1000) : (activeScale * 946.35);

        // Pre-calculate soda syrup/additive expansion factor if not hasRtdBase and SODA mode
        let sodaExpansionFactor = 1.0;
        if (drinkType === 'SODA' && !hasRtdBase) {
            const limit = 160.0 * activeScale;
            let linearTotal = 0;
            amountDisplays.forEach((el, idx) => {
                const originalAmount = parseFloat(el.getAttribute('data-original-amount'));
                const isDry = el.getAttribute('data-is-dry') === 'true';
                if (!isNaN(originalAmount) && !isDry) {
                    linearTotal += originalAmount * currentScale;
                }
            });
            if (linearTotal > 0) {
                const isSodaLiters = (Math.abs(activeScale - 1.0) < 0.01 || Math.abs(activeScale - 0.5) < 0.01);
                if (isSodaLiters || linearTotal < limit) {
                    sodaExpansionFactor = limit / linearTotal;
                }
            }
        }

        // Pre-calculate non-filler total volume for Soda/CRYO modes
        let nonFillerTotal = 0;
        amountDisplays.forEach((el, idx) => {
            if (idx !== firstRtdIndex) {
                const originalAmount = parseFloat(el.getAttribute('data-original-amount'));
                const isDry = el.getAttribute('data-is-dry') === 'true';
                if (!isNaN(originalAmount) && !isDry) {
                    nonFillerTotal += originalAmount * currentScale;
                }
            }
        });
        const fillerAmount = Math.max(0, bottleCapacity - nonFillerTotal);

        // Pre-calculate coffee bean budget split
        const coffeeBeanEls = amountDisplays.filter(el => el.getAttribute('data-ingredient-type') === 'COFFEE_BEAN');
        let totalOriginalBeans = 0;
        coffeeBeanEls.forEach(el => {
            const orig = parseFloat(el.getAttribute('data-original-amount'));
            if (!isNaN(orig)) totalOriginalBeans += orig;
        });

        let totalBaseGrams = 0;
        if (coffeeBaseType === 'espresso') {
            totalBaseGrams = 18.0 * coffeeBaseAmount;
        } else {
            totalBaseGrams = Math.round((7.0 / 6.0) * coffeeBaseAmount);
        }

        amountDisplays.forEach((el, idx) => {
            const originalAmount = parseFloat(el.getAttribute('data-original-amount'));
            if (isNaN(originalAmount)) return;
            
            const drinkType = el.getAttribute('data-drink-type');
            const ingredientType = el.getAttribute('data-ingredient-type');
            const isCoffee = drinkType === 'COFFEE';
            const isDry = el.getAttribute('data-is-dry') === 'true';
            
            if (isCoffee) {
                let amount = originalAmount;
                if (ingredientType === 'COFFEE_BEAN') {
                    const ratio = totalOriginalBeans > 0 ? (originalAmount / totalOriginalBeans) : 1.0;
                    amount = totalBaseGrams * ratio;
                    el.setAttribute('data-calculated-amount', amount);
                    if (coffeeBaseType === 'espresso') {
                        if (coffeeBeanEls.length > 1) {
                            el.innerHTML = `${(coffeeBaseAmount * ratio).toFixed(2)} shot${(coffeeBaseAmount * ratio) !== 1 ? 's' : ''} / ~${amount.toFixed(1)}g`;
                        } else {
                            el.innerHTML = `${coffeeBaseAmount} shot${coffeeBaseAmount !== 1 ? 's' : ''} / ~${Math.round(amount)}g`;
                        }
                    } else {
                        if (coffeeBeanEls.length > 1) {
                            el.innerHTML = `${(coffeeBaseAmount * ratio).toFixed(1)}oz brew / ~${amount.toFixed(1)}g`;
                        } else {
                            el.innerHTML = `${coffeeBaseAmount}oz brew / ~${amount.toFixed(0)}g`;
                        }
                    }
                } else if (isDry) {
                    const scaleFactor = coffeeSizeOz / savedSizeOz;
                    amount = originalAmount * scaleFactor;
                    el.setAttribute('data-calculated-amount', amount);
                    el.innerHTML = `${amount.toFixed(1)} g`;
                } else {
                    let scaleFactor = coffeeSizeOz / savedSizeOz;
                    
                    if (coffeeStyle === 'iced' && savedCoffeeStyle !== 'iced') {
                        scaleFactor *= 0.6;
                    } else if (coffeeStyle !== 'iced' && savedCoffeeStyle === 'iced') {
                        scaleFactor *= (1.0 / 0.6);
                    }
                    
                    const isVolumeFiller = (hasRtdBase ? (idx === firstRtdIndex) : (ingredientType === 'DAIRY'));
                    
                    if (coffeeStyle === 'espresso_shot') {
                        amount = (isVolumeFiller || ingredientType === 'ADDITIVE') ? 10.0 : 8.0;
                    } else if (coffeeBaseType === 'espresso' && isVolumeFiller) {
                        const liquidBudget = (coffeeStyle === 'iced') ? coffeeSizeOz * 0.6 : coffeeSizeOz;
                        const espressoVol = coffeeBaseAmount * 0.9;
                        const hotWaterVol = (coffeeEspressoHotMode === 'water') ? espressoVol : 0.0;
                        
                        let modifierVolOz = 0;
                        let numModifiers = 0;
                        let combinedSwe = 0;
                        amountDisplays.forEach((otherEl) => {
                            const otherIngType = otherEl.getAttribute('data-ingredient-type');
                            const otherIsDry = otherEl.getAttribute('data-is-dry') === 'true';
                            if (otherIngType !== 'COFFEE_BEAN' && otherIngType !== 'DAIRY' && !otherIsDry) {
                                numModifiers++;
                                combinedSwe += parseFloat(otherEl.getAttribute('data-sweetness') || 3.0);
                                const otherOrigAmt = parseFloat(otherEl.getAttribute('data-original-amount'));
                                if (!isNaN(otherOrigAmt)) {
                                    let otherAmt = otherOrigAmt * scaleFactor;
                                    modifierVolOz += otherAmt / 29.5735;
                                }
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
                        amount = Math.max(30.0, Math.round(dairyVol * 29.5735));
                    } else {
                        amount = originalAmount * scaleFactor;
                    }
                    
                    el.setAttribute('data-calculated-amount', amount);
                    let isCorrected = false;
                    let priVol = 0;
                    let texVol = 0;
                    let texName = "";
                    if (latestCoffeeChemistryData && latestCoffeeChemistryData.ingredients && latestCoffeeChemistryData.ingredients.payload_filler) {
                        const pf = latestCoffeeChemistryData.ingredients.payload_filler;
                        if (pf.is_corrected && isVolumeFiller) {
                            isCorrected = true;
                            priVol = Math.round(pf.primary_volume_oz * 29.5735);
                            texVol = Math.round(pf.texturizer_volume_oz * 29.5735);
                            texName = pf.texturizer_name;
                        }
                    }
                    if (isCorrected) {
                        el.innerHTML = `${priVol}ml (Primary Filler) & ${texName}: ${texVol}ml (Texture Anchor)`;
                    } else {
                        const displayVolume = Math.round(amount);
                        el.innerHTML = `${displayVolume} ml / ${formatImperialVolume(amount)}`;
                    }
                }
            } else {
                let amount;
                if (hasRtdBase && idx === firstRtdIndex) {
                    amount = fillerAmount;
                } else {
                    amount = originalAmount * currentScale;
                    if (drinkType === 'SODA' && !isDry) {
                        amount = amount * sodaExpansionFactor;
                    }
                }
                el.setAttribute('data-calculated-amount', amount);
                if (isDry) {
                    el.innerHTML = `${amount.toFixed(1)} g`;
                } else {
                    const displayVolume = Math.round(amount);
                    el.innerHTML = `${displayVolume} ml / ${formatImperialVolume(amount)}`;
                }
            }
        });

        const iceDetailEl = document.getElementById('iceDetailVolume');
        const iceCard = document.getElementById('iceCardContainer');
        if (iceCard) {
            iceCard.style.display = (coffeeStyle === 'iced') ? 'block' : 'none';
        }
        if (iceDetailEl) {
            const iceOz = getIceAmountOz(coffeeSizeOz);
            const iceMl = Math.round(iceOz * 29.5735);
            iceDetailEl.innerHTML = `${iceOz} oz / ~${iceMl} ml`;
        }

        const showHotWater = (drinkType === 'COFFEE' && coffeeBaseType === 'espresso' && coffeeEspressoHotMode === 'water');
        const hotWaterCard = document.getElementById('hotWaterCardContainer');
        if (hotWaterCard) {
            hotWaterCard.style.display = showHotWater ? 'block' : 'none';
        }
        const hotWaterDetailEl = document.getElementById('hotWaterDetailVolume');
        if (hotWaterDetailEl) {
            const hotWaterOz = (coffeeBaseAmount * 0.9).toFixed(1);
            const hotWaterMl = Math.round(hotWaterOz * 29.5735);
            hotWaterDetailEl.innerHTML = `${hotWaterOz} oz / ~${hotWaterMl} ml`;
        }

        const waterDetailEl = document.getElementById('waterDetailVolume');
        if (waterDetailEl) {
            let totalSyrup = 0;
            amountDisplays.forEach(el => {
                const originalAmount = parseFloat(el.getAttribute('data-original-amount'));
                const isDry = el.getAttribute('data-is-dry') === 'true';
                if (!isNaN(originalAmount) && !isDry) {
                    totalSyrup += originalAmount * currentScale;
                }
            });
            const savedScale = savedSizeOz / 32.0;
            const activeScale = currentScale * savedScale;
            const bottleCapacity = activeScale * 946.35;
            const waterMl = Math.max(0, bottleCapacity - totalSyrup);
            waterDetailEl.innerHTML = `${Math.round(waterMl)} ml / ${formatImperialVolume(waterMl)}`;
        }

        const sodaWaterDetailEl = document.getElementById('sodaWaterDetailVolume');
        if (sodaWaterDetailEl) {
            let totalSyrup = 0;
            amountDisplays.forEach(el => {
                const originalAmount = parseFloat(el.getAttribute('data-original-amount'));
                const isDry = el.getAttribute('data-is-dry') === 'true';
                if (!isNaN(originalAmount) && !isDry) {
                    let amt = originalAmount * currentScale;
                    if (drinkType === 'SODA' && !hasRtdBase) {
                        amt = amt * sodaExpansionFactor;
                    }
                    totalSyrup += amt;
                }
            });
            let savedScale = 1.0;
            if (savedSizeOz === 12.0) savedScale = 0.355;
            else if (savedSizeOz === 16.9) savedScale = 0.5;
            
            const activeScale = currentScale * savedScale;
            const bottleCapacity = activeScale * 1000;
            const waterMl = Math.max(0, bottleCapacity - totalSyrup);
            sodaWaterDetailEl.innerHTML = `${Math.round(waterMl)} ml / ${formatImperialVolume(waterMl)}`;
        }

        if (drinkType === 'COFFEE') {
            fetchCoffeeChemistry();
        } else if (drinkType === 'SODA') {
            fetchSodaChemistry();
        } else if (drinkType === 'CRYO') {
            fetchCryoChemistry();
        }
    }

    async function fetchSodaChemistry() {
        if (drinkType !== 'SODA') return;
        
        const chemistryContainer = document.getElementById('sodaChemistryAnalysis');
        if (!chemistryContainer) return;
        
        const ingredients = [];
        document.querySelectorAll('.amount-display').forEach(el => {
            const id = el.getAttribute('data-id');
            if (!id) return;
            
            ingredients.push({
                id: id,
                name: el.getAttribute('data-name'),
                ingredient_type: el.getAttribute('data-ingredient-type'),
                intensity: parseInt(el.getAttribute('data-intensity')),
                acidity: parseInt(el.getAttribute('data-acidity')),
                bitterness: parseInt(el.getAttribute('data-bitterness')),
                complexity: parseInt(el.getAttribute('data-complexity')),
                acidity_score: parseInt(el.getAttribute('data-acidity-score') || 3),
                bitterness_score: parseInt(el.getAttribute('data-bitterness-score') || 3),
                flavor_notes: el.getAttribute('data-flavor-notes') || '',
                amount: parseFloat(el.getAttribute('data-calculated-amount') || el.getAttribute('data-original-amount')),
                is_primary: el.getAttribute('data-is-primary') === 'true'
            });
        });

        let savedScale = 1.0;
        if (savedSizeOz === 12.0) savedScale = 0.355;
        else if (savedSizeOz === 16.9) savedScale = 0.5;

        const activeScale = currentScale * savedScale;

        try {
            const chemistryPromise = fetch('/api/soda/chemistry/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': window.CSRF_TOKEN },
                body: JSON.stringify({
                    sweetness_style: currentSweetnessStyle,
                    bottle_scale: activeScale,
                    ingredients: ingredients.map(ing => {
                        const copy = { ...ing };
                        copy.ingredient_type = ing.ingredient_type || ing.type;
                        copy.is_primary = ing.is_primary;
                        return copy;
                    })
                })
            });

            const chemRes = await chemistryPromise;
            const data = await chemRes.json();
            
            if (data.drink_metrics && data.drink_metrics.sweetness_style) {
                currentSweetnessStyle = data.drink_metrics.sweetness_style;
                document.getElementById('sweetnessCrisp')?.classList.remove('active-lab-mode');
                document.getElementById('sweetnessCraft')?.classList.remove('active-lab-mode');
                document.getElementById('sweetnessFountain')?.classList.remove('active-lab-mode');
                
                if (currentSweetnessStyle === 'CRISP') document.getElementById('sweetnessCrisp')?.classList.add('active-lab-mode');
                if (currentSweetnessStyle === 'CRAFT') document.getElementById('sweetnessCraft')?.classList.add('active-lab-mode');
                if (currentSweetnessStyle === 'FOUNTAIN') document.getElementById('sweetnessFountain')?.classList.add('active-lab-mode');
            }

            let validationBadge = '';
            if (data.recipe_validation && !data.recipe_validation.toLowerCase().includes("pass")) {
                let badgeClass = "bg-success bg-opacity-10 border-success text-success";
                if (data.recipe_validation.toLowerCase().includes("warning")) {
                    badgeClass = "bg-warning bg-opacity-10 border-warning text-warning";
                } else if (data.recipe_validation.toLowerCase().includes("fail")) {
                    badgeClass = "bg-danger bg-opacity-10 border-danger text-danger";
                }
                validationBadge = `
                    <div class="alert ${badgeClass} border small py-2 d-flex align-items-center gap-2 mb-3">
                        <i class="bi bi-info-circle"></i>
                        <span class="fw-bold">${data.recipe_validation}</span>
                    </div>
                `;
            }

            let prepStepsHtml = '';
            if (data.preparation_steps && data.preparation_steps.length > 0) {
                prepStepsHtml = `
                    <div class="pt-2 border-top border-white border-opacity-5">
                        <span class="readout-label d-block text-dim mb-2" style="font-size: 0.65rem;">PREPARATION STEPS</span>
                        <ol class="small text-white opacity-90 ps-3 mb-3">
                            ${data.preparation_steps.map(step => `<li class="mb-1">${step}</li>`).join('')}
                        </ol>
                    </div>
                `;
            }

            let targetLabel = '';
            if (Math.abs(activeScale - 1.0) < 0.01) targetLabel = '1.0L Bottle';
            else if (Math.abs(activeScale - 0.5) < 0.01) targetLabel = '0.5L Bottle';
            else if (Math.abs(activeScale - 0.355) < 0.01) targetLabel = '12oz Glass';

            chemistryContainer.innerHTML = `
                ${validationBadge}
                
                <div class="row g-4 mb-4 print-hide">
                    <div class="col-md-4">
                        <label class="readout-label mb-1">Calculated Sweetness</label>
                        <div class="fs-4 fw-bold text-white mb-2">${data.extraction_analysis.sweetness || 0}/5.0</div>
                        <div class="progress bg-white bg-opacity-5" style="height: 6px; border-radius: 100px;">
                            <div class="progress-bar" style="width: ${(data.extraction_analysis.sweetness || 0)/5 * 100}%; background: var(--berry-punch); box-shadow: 0 0 10px var(--berry-punch);"></div>
                        </div>
                    </div>
                    <div class="col-md-4">
                        <label class="readout-label mb-1">Calculated Acidity</label>
                        <div class="fs-4 fw-bold text-white mb-2">${data.extraction_analysis.acidity || 0}/5.0</div>
                        <div class="progress bg-white bg-opacity-5" style="height: 6px; border-radius: 100px;">
                            <div class="progress-bar" style="width: ${(data.extraction_analysis.acidity || 0)/5 * 100}%; background: var(--citrus-yellow); box-shadow: 0 0 10px var(--citrus-yellow);"></div>
                        </div>
                    </div>
                    <div class="col-md-4">
                        <label class="readout-label mb-1">Calculated Bitterness</label>
                        <div class="fs-4 fw-bold text-white mb-2">${data.extraction_analysis.bitterness || 0}/5.0</div>
                        <div class="progress bg-white bg-opacity-5" style="height: 6px; border-radius: 100px;">
                            <div class="progress-bar" style="width: ${(data.extraction_analysis.bitterness || 0)/5 * 100}%; background: #4e342e; box-shadow: 0 0 10px #4e342e;"></div>
                        </div>
                    </div>
                </div>

                <div class="pt-2 border-top border-white border-opacity-5 print-hide">
                    <span class="readout-label d-block text-dim mb-1" style="font-size: 0.65rem;">MIXOLOGIST RECOMMENDATION</span>
                    <p class="mb-0 small text-dim italic mb-3">"${data.barista_notes}"</p>
                </div>

                ${prepStepsHtml}

                </div>
            `;

            // Also, update the Carbonated Water card and ingredient displays with the returned volumes!
            const waterEl = document.getElementById('sodaWaterDetailVolume');
            if (waterEl && data.ingredients && data.ingredients.carbonated_water) {
                const cwVolume = data.ingredients.carbonated_water.volume_ml;
                waterEl.innerHTML = `${Math.round(cwVolume)} ml / ${formatImperialVolume(cwVolume)}`;
            }

            document.querySelectorAll('.amount-display').forEach(el => {
                const id = el.getAttribute('data-id');
                if (!id) return;
                const mod = (data.ingredients.modifiers || []).find(m => m.id == id);
                if (mod) {
                    const isDry = el.getAttribute('data-is-dry') === 'true';
                    const modVol = mod.volume_ml;
                    el.setAttribute('data-calculated-amount', modVol);
                    if (isDry) {
                        el.innerHTML = `${modVol.toFixed(1)} g`;
                    } else {
                        el.innerHTML = `${Math.round(modVol)} ml / ${formatImperialVolume(modVol)}`;
                    }
                }
            });

        } catch (err) {
            console.error("Error fetching soda chemistry:", err);
        }
    }

    async function fetchCryoChemistry() {
        if (drinkType !== 'CRYO') return;
        
        const chemistryContainer = document.getElementById('cryoChemistryAnalysis');
        if (!chemistryContainer) return;
        
        const ingredients = [];
        document.querySelectorAll('.amount-display').forEach(el => {
            const id = el.getAttribute('data-id');
            if (!id) return;
            
            ingredients.push({
                id: id,
                name: el.getAttribute('data-name'),
                ingredient_type: el.getAttribute('data-ingredient-type'),
                intensity: parseInt(el.getAttribute('data-intensity')),
                acidity: parseInt(el.getAttribute('data-acidity')),
                bitterness: parseInt(el.getAttribute('data-bitterness')),
                complexity: parseInt(el.getAttribute('data-complexity')),
                acidity_score: parseInt(el.getAttribute('data-acidity-score') || 3),
                bitterness_score: parseInt(el.getAttribute('data-bitterness-score') || 3),
                sweetness_score: parseInt(el.getAttribute('data-sweetness') || 3),
                sweetness: parseInt(el.getAttribute('data-sweetness') || 3),
                flavor_notes: el.getAttribute('data-flavor-notes') || '',
                amount: parseFloat(el.getAttribute('data-calculated-amount') || el.getAttribute('data-original-amount'))
            });
        });

        let savedScale = savedSizeOz / 32.0;
        const activeScale = currentScale * savedScale;

        try {
            const chemistryPromise = fetch('/api/cryo/chemistry/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': window.CSRF_TOKEN },
                body: JSON.stringify({
                    bottle_scale: activeScale,
                    ingredients: ingredients.map(ing => {
                        const copy = { ...ing };
                        copy.ingredient_type = ing.ingredient_type || ing.type;
                        return copy;
                    })
                })
            });

            const chemRes = await chemistryPromise;
            const data = await chemRes.json();
            let validationBadge = '';
            if (data.recipe_validation && !data.recipe_validation.toLowerCase().includes("pass")) {
                let badgeClass = "bg-success bg-opacity-10 border-success text-success";
                if (data.recipe_validation.toLowerCase().includes("warning")) {
                    badgeClass = "bg-warning bg-opacity-10 border-warning text-warning";
                } else if (data.recipe_validation.toLowerCase().includes("fail")) {
                    badgeClass = "bg-danger bg-opacity-10 border-danger text-danger";
                }
                validationBadge = `
                    <div class="alert ${badgeClass} border small py-2 d-flex align-items-center gap-2 mb-3">
                        <i class="bi bi-info-circle"></i>
                        <span class="fw-bold">${data.recipe_validation}</span>
                    </div>
                `;
            }

            let prepStepsHtml = '';
            if (data.preparation_steps && data.preparation_steps.length > 0) {
                prepStepsHtml = `
                    <div class="pt-2 border-top border-white border-opacity-5">
                        <span class="readout-label d-block text-dim mb-2" style="font-size: 0.65rem;">PREPARATION STEPS</span>
                        <ol class="small text-white opacity-90 ps-3 mb-3">
                            ${data.preparation_steps.map(step => `<li class="mb-1">${step}</li>`).join('')}
                        </ol>
                    </div>
                `;
            }

            let targetLabel = '';
            if (Math.abs(activeScale - 0.5) < 0.01) targetLabel = '16oz Batch (473ml)';
            else if (Math.abs(activeScale - 1.0) < 0.01) targetLabel = '32oz Batch (946ml)';
            else if (Math.abs(activeScale - 1.5) < 0.01) targetLabel = '48oz Batch (1420ml)';
            else if (Math.abs(activeScale - 2.0) < 0.01) targetLabel = '64oz Batch (1892ml)';

            chemistryContainer.innerHTML = `
                ${validationBadge}
                
                <div class="row g-4 mb-4 print-hide">
                    <div class="col-md-4">
                        <label class="readout-label mb-1">Perceived Sweetness</label>
                        <div class="fs-4 fw-bold text-white mb-2">${data.extraction_analysis.sweetness || 0}/5.0</div>
                        <div class="progress bg-white bg-opacity-5" style="height: 6px; border-radius: 100px;">
                            <div class="progress-bar" style="width: ${(data.extraction_analysis.sweetness || 0)/5 * 100}%; background: var(--berry-punch); box-shadow: 0 0 10px var(--berry-punch);"></div>
                        </div>
                    </div>
                    <div class="col-md-4">
                        <label class="readout-label mb-1">Calculated Acidity</label>
                        <div class="fs-4 fw-bold text-white mb-2">${data.extraction_analysis.acidity || 0}/5.0</div>
                        <div class="progress bg-white bg-opacity-5" style="height: 6px; border-radius: 100px;">
                            <div class="progress-bar" style="width: ${(data.extraction_analysis.acidity || 0)/5 * 100}%; background: var(--citrus-yellow); box-shadow: 0 0 10px var(--citrus-yellow);"></div>
                        </div>
                    </div>
                    <div class="col-md-4">
                        <label class="readout-label mb-1">Calculated Bitterness</label>
                        <div class="fs-4 fw-bold text-white mb-2">${data.extraction_analysis.bitterness || 0}/5.0</div>
                        <div class="progress bg-white bg-opacity-5" style="height: 6px; border-radius: 100px;">
                            <div class="progress-bar" style="width: ${(data.extraction_analysis.bitterness || 0)/5 * 100}%; background: #4e342e; box-shadow: 0 0 10px #4e342e;"></div>
                        </div>
                    </div>
                </div>

                <div class="pt-2 border-top border-white border-opacity-5 print-hide">
                    <span class="readout-label d-block text-dim mb-1" style="font-size: 0.65rem;">MIXOLOGIST RECOMMENDATION</span>
                    <p class="mb-0 small text-dim italic mb-3">"${data.mixologist_notes}"</p>
                </div>

                ${prepStepsHtml}

                </div>
            `;

            // Update the Volume Filler card
            const fillerNameEl = document.getElementById('cryoFillerName');
            const fillerVolumeEl = document.getElementById('cryoFillerDetailVolume');
            if (data.ingredients && data.ingredients.filler) {
                const fillerVal = data.ingredients.filler.volume_ml;
                if (fillerNameEl) {
                    fillerNameEl.innerHTML = `${data.ingredients.filler.name} <i class="bi bi-droplets text-lab-accent ms-1"></i>`;
                }
                if (fillerVolumeEl) {
                    fillerVolumeEl.innerHTML = `${Math.round(fillerVal)} ml / ${formatImperialVolume(fillerVal)}`;
                }
            }

            // Update individual modifier display volumes with exact calculated values
            document.querySelectorAll('.amount-display').forEach(el => {
                const id = el.getAttribute('data-id');
                if (!id) return;
                const mod = (data.ingredients.modifiers || []).find(m => m.id == id);
                if (mod) {
                    const isDry = el.getAttribute('data-is-dry') === 'true';
                    const modVol = mod.volume_ml;
                    el.setAttribute('data-calculated-amount', modVol);
                    if (isDry) {
                        el.innerHTML = `${modVol.toFixed(1)} g`;
                    } else {
                        el.innerHTML = `${Math.round(modVol)} ml / ${formatImperialVolume(modVol)}`;
                    }
                }
            });

        } catch (err) {
            console.error("Error fetching cryo chemistry:", err);
        }
    }

    async function fetchCoffeeChemistry() {
        if (drinkType !== 'COFFEE') return;
        
        const chemistryContainer = document.getElementById('coffeeChemistryAnalysis');
        if (!chemistryContainer) return;
        
        const ingredients = [];
        document.querySelectorAll('.amount-display').forEach(el => {
            const id = el.getAttribute('data-id');
            if (!id) return;
            
            ingredients.push({
                id: id,
                name: el.getAttribute('data-name'),
                ingredient_type: el.getAttribute('data-ingredient-type'),
                intensity: parseInt(el.getAttribute('data-intensity')),
                acidity: parseInt(el.getAttribute('data-acidity')),
                bitterness: parseInt(el.getAttribute('data-bitterness')),
                complexity: parseInt(el.getAttribute('data-complexity')),
                body_intensity: parseInt(el.getAttribute('data-body-intensity') || 3),
                acidity_score: parseInt(el.getAttribute('data-acidity-score') || 3),
                bitterness_score: parseInt(el.getAttribute('data-bitterness-score') || 3),
                flavor_notes: el.getAttribute('data-flavor-notes') || '',
                is_decaf: el.getAttribute('data-is-decaf') === 'true',
                amount: parseFloat(el.getAttribute('data-calculated-amount') || el.getAttribute('data-original-amount'))
            });
        });

        let drinkCategory = "Hot Coffee";
        if (coffeeStyle === 'iced') {
            drinkCategory = "Iced Coffee";
        } else if (coffeeStyle === 'espresso_shot') {
            drinkCategory = "Pure Espresso / Short Milk";
        }

        try {
            const mappedIngredients = ingredients.map(ing => {
                const copy = { ...ing };
                if (copy.ingredient_type === 'COFFEE_BEAN') {
                    copy.coffee_base_type = coffeeBaseType;
                }
                return copy;
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

            const chemRes = await chemistryPromise;
            const data = await chemRes.json();
            latestCoffeeChemistryData = data;
            updateAmounts();
            let validationBadge = '';
            if (data.recipe_validation && !data.recipe_validation.toLowerCase().includes("pass")) {
                let badgeClass = "bg-success bg-opacity-10 border-success text-success";
                if (data.recipe_validation.toLowerCase().includes("warning")) {
                    badgeClass = "bg-warning bg-opacity-10 border-warning text-warning";
                } else if (data.recipe_validation.toLowerCase().includes("fail")) {
                    badgeClass = "bg-danger bg-opacity-10 border-danger text-danger";
                }
                validationBadge = `
                    <div class="alert ${badgeClass} border small py-2 d-flex align-items-center gap-2 mb-3">
                        <i class="bi bi-info-circle"></i>
                        <span class="fw-bold">${data.recipe_validation}</span>
                    </div>
                `;
            }

            const metrics = data.aggregate_base_metrics || {};
            const notesHtml = (metrics.combined_notes || []).map(n => `<span class="badge-fizz bg-secondary text-white me-1 mb-1">${n}</span>`).join('');

            let prepStepsHtml = '';
            if (data.preparation_steps && data.preparation_steps.length > 0) {
                prepStepsHtml = `
                    <div class="pt-2 border-top border-white border-opacity-5">
                        <span class="readout-label d-block text-dim mb-2" style="font-size: 0.65rem;">PREPARATION STEPS (SOLUBILITY)</span>
                        <ol class="small text-white opacity-90 ps-3 mb-3">
                            ${data.preparation_steps.map(step => `<li class="mb-1">${step}</li>`).join('')}
                        </ol>
                    </div>
                `;
            }

            chemistryContainer.innerHTML = `
                ${validationBadge}
                
                <div class="row g-4 mb-4 print-hide">
                    <div class="col-md-4">
                        <label class="readout-label mb-1">Calculated Body</label>
                        <div class="fs-4 fw-bold text-white mb-2">${metrics.calculated_body || 0}/5.0</div>
                        <div class="progress bg-white bg-opacity-5" style="height: 6px; border-radius: 100px;">
                            <div class="progress-bar" style="width: ${(metrics.calculated_body || 0)/5 * 100}%; background: var(--fizz-amber); box-shadow: 0 0 10px var(--fizz-amber);"></div>
                        </div>
                    </div>
                    <div class="col-md-4">
                        <label class="readout-label mb-1">Calculated Acidity</label>
                        <div class="fs-4 fw-bold text-white mb-2">${metrics.calculated_acidity || 0}/5.0</div>
                        <div class="progress bg-white bg-opacity-5" style="height: 6px; border-radius: 100px;">
                            <div class="progress-bar" style="width: ${(metrics.calculated_acidity || 0)/5 * 100}%; background: var(--citrus-yellow); box-shadow: 0 0 10px var(--citrus-yellow);"></div>
                        </div>
                    </div>
                    <div class="col-md-4">
                        <label class="readout-label mb-1">Calculated Bitterness</label>
                        <div class="fs-4 fw-bold text-white mb-2">${metrics.calculated_bitterness || 0}/5.0</div>
                        <div class="progress bg-white bg-opacity-5" style="height: 6px; border-radius: 100px;">
                            <div class="progress-bar" style="width: ${(metrics.calculated_bitterness || 0)/5 * 100}%; background: #4e342e; box-shadow: 0 0 10px #4e342e;"></div>
                        </div>
                    </div>
                </div>

                <div class="row g-3 mb-4">
                    <div class="col-md-6">
                        <div class="readout-card p-2">
                            <span class="readout-label d-block text-dim" style="font-size: 0.6rem;">LIQUID BUDGET</span>
                            <div class="fw-bold fs-5 text-white">${data.liquid_budget_oz} oz</div>
                        </div>
                    </div>
                    <div class="col-md-6">
                        <div class="readout-card p-2">
                            <span class="readout-label d-block text-dim" style="font-size: 0.6rem;">ICE VOLUME</span>
                            <div class="fw-bold fs-5 text-white">${data.ice_volume_oz} oz</div>
                        </div>
                    </div>
                </div>

                <div class="mb-3 pt-2 border-top border-white border-opacity-5">
                    <span class="readout-label d-block text-dim mb-1" style="font-size: 0.65rem;">COMBINED FLAVOR NOTES</span>
                    <div class="d-flex flex-wrap">${notesHtml || '<span class="text-dim">None</span>'}</div>
                </div>

                <div class="pt-2 border-top border-white border-opacity-5 print-hide">
                    <span class="readout-label d-block text-dim mb-1" style="font-size: 0.65rem;">BARISTA RECOMMENDATION</span>
                    <p class="mb-0 small text-dim italic mb-3">"${data.barista_notes}"</p>
                </div>

                ${prepStepsHtml}

                </div>
            `;
        } catch (err) {
            console.error("Error fetching coffee chemistry:", err);
        }
    }

    document.addEventListener('DOMContentLoaded', function() {
        if (drinkType === 'SODA') {
            if (savedSizeOz === 12.0) {
                setBottleScale(0.355, 'scale12oz');
            } else if (savedSizeOz === 16.9) {
                setBottleScale(0.5, 'scale05L');
            } else {
                setBottleScale(1.0, 'scale1L');
            }
        } else if (drinkType === 'CRYO') {
            if (savedSizeOz === 16.0) {
                setBottleScale(0.5, 'scale16oz');
            } else if (savedSizeOz === 48.0) {
                setBottleScale(1.5, 'scale48oz');
            } else if (savedSizeOz === 64.0) {
                setBottleScale(2.0, 'scale64oz');
            } else {
                setBottleScale(1.0, 'scale32oz');
            }
        } else if (drinkType === 'COFFEE') {
            setCoffeeStyle(coffeeStyle);
            setCoffeeBaseType(coffeeBaseType);
            setCoffeeSize(coffeeSizeOz);
        } else {
            updateAmounts();
        }
        const ratingUI = document.getElementById('ratingUI');
        if (ratingUI) {
            ratingUI.addEventListener('click', function(e) {
                const star = e.target.closest('.rating-star');
                if (!star) return;
                
                const recipeId = this.dataset.recipeId;
                const rating = parseInt(star.dataset.rating);
                rateRecipe(recipeId, rating);
            });
        }

        const mealieBtn = document.getElementById('mealieBtn');
        if (mealieBtn) {
            mealieBtn.addEventListener('click', function() {
                exportToMealie(this.dataset.recipeId);
            });
        }

        const saveCatsBtn = document.querySelector('.btn-save-recipe-cats');
        if (saveCatsBtn) {
            saveCatsBtn.addEventListener('click', function() {
                saveRecipeCategories(this.dataset.recipeId);
            });
        }
    });

function rateRecipe(recipeId, rating) {
    fetch(`/api/recipes/${recipeId}/rate/`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': window.CSRF_TOKEN
        },
        body: JSON.stringify({ rating: rating })
    })
    .then(response => response.json())
    .then(data => {
        if (!data.error) {
            const stars = document.querySelectorAll('.rating-star');
            stars.forEach(star => {
                const starRating = parseInt(star.getAttribute('data-rating'));
                if (starRating <= rating) {
                    star.classList.remove('bi-star', 'text-muted');
                    star.classList.add('bi-star-fill', 'text-warning', 'active');
                } else {
                    star.classList.remove('bi-star-fill', 'text-warning', 'active');
                    star.classList.add('bi-star', 'text-muted');
                }
            });
            document.getElementById('ratingText').textContent = `${rating} Stars`;
        }
    });
}

function saveRecipeCategories(recipeId) {
    const btn = document.querySelector('.btn-save-recipe-cats');
    const originalText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Saving...';

    const categoryIds = [...document.querySelectorAll('.recipe-cat-check:checked')]
        .map(el => parseInt(el.value));

    fetch(`/api/recipes/${recipeId}/categories/`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': window.CSRF_TOKEN
        },
        body: JSON.stringify({category_ids: categoryIds})
    })
    .then(r => r.json())
    .then(data => {
        if (data.status === 'updated') {
            window.location.reload();
        } else {
            btn.disabled = false;
            btn.innerHTML = originalText;
            alert(data.error || "Save failed.");
        }
    })
    .catch(err => {
        btn.disabled = false;
        btn.innerHTML = originalText;
        alert("A network error occurred.");
    });
}

function pollTask(taskId, onProgress, onSuccess, onFailure) {
    const interval = setInterval(() => {
        fetch(`/api/tasks/${taskId}/`)
        .then(r => {
            if (!r.ok) throw new Error("Task status request rejected by system.");
            return r.json();
        })
        .then(data => {
            if (data.status === 'SUCCESS') {
                clearInterval(interval);
                onSuccess(data.result_data);
            } else if (data.status === 'FAILURE') {
                clearInterval(interval);
                onFailure(data.error_message);
            } else {
                onProgress(data.progress);
            }
        })
        .catch(err => {
            clearInterval(interval);
            onFailure(err.message || "Laboratory signal loss.");
        });
    }, 1000);
}

function exportToMealie(recipeId) {
    const btn = document.getElementById('mealieBtn');
    const originalHtml = btn.innerHTML;
    
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Initializing...';
    
    fetch(`/api/recipes/${recipeId}/export/`, {
        method: 'POST',
        headers: {
            'X-CSRFToken': window.CSRF_TOKEN
        }
    })
    .then(r => {
        if (r.status === 202) {
            return r.json().then(data => {
                pollTask(data.task_id, 
                    (progress) => {
                        btn.innerHTML = `<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Syncing (${progress}%)...`;
                    },
                    (result) => {
                        btn.disabled = false;
                        btn.innerHTML = '<i class="bi bi-check-lg"></i> Synced!';
                        btn.classList.replace('btn-primary', 'btn-success');
                        setTimeout(() => {
                            btn.innerHTML = originalHtml;
                            btn.classList.replace('btn-success', 'btn-primary');
                        }, 3000);
                    },
                    (errorMsg) => {
                        btn.disabled = false;
                        btn.innerHTML = originalHtml;
                        alert("Export Failed: " + errorMsg);
                    }
                );
            });
        } else {
            return r.json().then(data => {
                btn.disabled = false;
                btn.innerHTML = originalHtml;
                alert("Export Failed: " + (data.error || "Internal Error"));
            });
        }
    })
    .catch(err => {
        btn.disabled = false;
        btn.innerHTML = originalHtml;
        alert("A network error occurred while contacting the laboratory server.");
    });
}
