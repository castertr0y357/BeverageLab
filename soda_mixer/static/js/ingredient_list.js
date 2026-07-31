// Toggle Coffee-Specific Fields Function
    function toggleCoffeeFields(prefix) {
        const stateSelect = document.getElementById(prefix + 'PhysicalState');
        const coffeeFields = document.getElementById(prefix + 'CoffeeFields');
        if (stateSelect && coffeeFields) {
            if (stateSelect.value === 'SOLID_EXTRACTABLE') {
                coffeeFields.style.display = 'block';
            } else {
                coffeeFields.style.display = 'none';
            }
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        const addStateSelect = document.getElementById('addPhysicalState');
        if (addStateSelect) {
            addStateSelect.addEventListener('change', () => toggleCoffeeFields('add'));
        }
        const editStateSelect = document.getElementById('editPhysicalState');
        if (editStateSelect) {
            editStateSelect.addEventListener('change', () => toggleCoffeeFields('edit'));
        }

        // 1. Edit Material Modal Logic
        document.querySelectorAll('.btn-edit-material').forEach(btn => {
            btn.addEventListener('click', function () {
                const d = this.dataset;
                document.getElementById('editIngredientForm').action = `/ingredients/${d.id}/edit/`;
                document.getElementById('editName').value = d.name;
                document.getElementById('editBrand').value = d.brand || '';
                document.getElementById('editPhysicalState').value = d.physicalState || 'SYRUP';
                document.getElementById('editMixologyFunction').value = d.mixologyFunction || 'FLAVORING';
                document.getElementById('editCategory').value = d.category;
                document.getElementById('editInt').value = d.intensity;
                document.getElementById('editSwt').value = d.sweetness;
                document.getElementById('editAcd').value = d.acidity;
                document.getElementById('editBit').value = d.bitterness;
                document.getElementById('editCpx').value = d.complexity;
                document.getElementById('editBaseSuit').value = d.baseSuitability;
                document.getElementById('editAccentSuit').value = d.accentSuitability;
                document.getElementById('editDesc').value = d.description;
                document.getElementById('editAINotes').value = d.aiNotes || '';
                document.getElementById('editFavorite').checked = d.favorite === 'true';
                
                // Coffee fields populator
                document.getElementById('editOrigin').value = d.origin || '';
                document.getElementById('editRoaster').value = d.roaster || '';
                document.getElementById('editProcess').value = d.process || '';
                document.getElementById('editRoastLevel').value = d.roastLevel || 'MEDIUM';
                document.getElementById('editIsDecaf').checked = d.isDecaf === 'true';
                document.getElementById('editBodyIntensity').value = d.bodyIntensity || 3;
                document.getElementById('editAcidityScore').value = d.acidityScore || 3;
                document.getElementById('editBitternessScore').value = d.bitternessScore || 3;
                document.getElementById('editFlavorNotes').value = d.flavorNotes || '';
                
                toggleCoffeeFields('edit');
                
                // Set system checkboxes
                const systems = d.systems ? d.systems.split(',') : [];
                document.querySelectorAll('.sys-edit-check').forEach(chk => {
                    chk.checked = systems.includes(chk.value);
                });

                new bootstrap.Modal(document.getElementById('editIngredientModal')).show();
            });
        });

        // 2. Inventory Toggle Logic
        document.querySelectorAll('.inventory-toggle').forEach(chk => {
            chk.addEventListener('change', function () {
                const ingredientId = this.dataset.ingredientId;
                const isChecked = this.checked;
                const checkbox = this;

                fetch(`/api/ingredients/${ingredientId}/toggle_inventory/`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': window.CSRF_TOKEN
                    },
                    body: JSON.stringify({ is_in_inventory: isChecked })
                })
                .then(response => response.json())
                .then(data => {
                    if (data.error) {
                        checkbox.checked = !isChecked;
                        alert('Failed to update inventory status: ' + data.error);
                    }
                })
                .catch(err => {
                    checkbox.checked = !isChecked;
                    alert('A network error occurred while updating inventory status.');
                });
            });
        });

        // 3. Add Recipe Category Logic
        const btnAddCat = document.getElementById('btnAddRecipeCat');
        if (btnAddCat) {
            btnAddCat.addEventListener('click', function () {
                const name = document.getElementById('newRecipeCatName').value;
                const color = document.getElementById('newRecipeCatColor').value;
                if (!name) return;

                fetch('/api/categories/create/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': window.CSRF_TOKEN
                    },
                    body: JSON.stringify({ name, color })
                })
                    .then(response => response.json())
                    .then(data => {
                        if (data.status === 'success') location.reload();
                        else alert(data.error);
                    });
            });
        }

        // 4. Delete Recipe Category Logic
        document.querySelectorAll('.btn-delete-recipe-cat').forEach(btn => {
            btn.addEventListener('click', function () {
                if (!confirm('Delete this tag? Recipes using it will lose the tag.')) return;
                const id = this.dataset.id;
                const li = this.closest('li');

                fetch(`/api/categories/${id}/delete/`, {
                    method: 'POST',
                    headers: { 'X-CSRFToken': window.CSRF_TOKEN }
                })
                    .then(response => response.json())
                    .then(data => {
                        if (data.status === 'success') li.remove();
                        else alert(data.error);
                    });
            });
        });

        // 5. Delete Ingredient Profile Logic
        document.querySelectorAll('.btn-delete-ing-profile').forEach(btn => {
            btn.addEventListener('click', function () {
                const profile = this.dataset.profile;
                if (!confirm(`Reassign all ingredients in '${profile}' to 'other'?`)) return;

                fetch('/api/ingredient-profiles/delete/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': window.CSRF_TOKEN
                    },
                    body: JSON.stringify({ profile })
                })
                    .then(response => response.json())
                    .then(data => {
                        if (data.status === 'success') location.reload();
                        else alert(data.error);
                    });
            });
        });
    });

    async function synthesizeProfile(prefix, btn) {
        const nameInput = document.getElementById(prefix + 'Name');
        const brandInput = document.getElementById(prefix + 'Brand');
        const descInput = document.getElementById(prefix + 'Desc') || { value: '' };

        if (!nameInput) {
            console.error('[synthesizeProfile] Could not find name input for prefix:', prefix);
            alert('Comms Failure: Modal input not found. Please try closing and reopening the form.');
            return;
        }

        const name = nameInput.value.trim();
        const brand = brandInput ? brandInput.value.trim() : '';
        const description = descInput.value.trim();

        if (!name) {
            alert("Identification Required: Please enter a material name for chemical analysis.");
            return;
        }

        const originalHtml = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Analyzing...';

        try {
            const response = await fetch('/api/ai/analyze-ingredient/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': window.CSRF_TOKEN
                },
                body: JSON.stringify({ name, brand, description })
            });
            if (!response.ok) {
                const errText = await response.text();
                console.error('[synthesizeProfile] Server returned HTTP', response.status, errText.substring(0, 500));
                alert(`Analysis Error: Server returned HTTP ${response.status}. Check console for details.`);
                return;
            }
            const data = await response.json();
            
            if (data.status === 'success') {
                const profile = data.profile;
                const fields = {
                    'Int': profile.intensity,
                    'Swt': profile.sweetness,
                    'Acd': profile.acidity,
                    'Bit': profile.bitterness,
                    'Cpx': profile.complexity,
                    'BaseSuit': profile.base_suitability || 3.0,
                    'AccentSuit': profile.accent_suitability || 3.0
                };

                for (const [suffix, value] of Object.entries(fields)) {
                    const el = document.getElementById(prefix + suffix);
                    if (el) {
                        if (suffix.includes('Suit')) {
                            const parsedSuit = parseFloat(value);
                            el.value = isNaN(parsedSuit) ? '3.0' : parsedSuit.toFixed(1);
                        } else {
                            const parsedVal = parseFloat(value);
                            el.value = isNaN(parsedVal) ? 3 : Math.round(parsedVal);
                        }
                        el.classList.add('is-valid');
                        setTimeout(() => el.classList.remove('is-valid'), 2000);
                    }
                }

                const categoryEl = document.getElementById(prefix + 'Category');
                if (categoryEl && profile.category) {
                    categoryEl.value = profile.category;
                    categoryEl.classList.add('is-valid');
                    setTimeout(() => categoryEl.classList.remove('is-valid'), 2000);
                }

                const physicalStateEl = document.getElementById(prefix + 'PhysicalState');
                if (physicalStateEl && profile.physical_state) {
                    physicalStateEl.value = profile.physical_state;
                    physicalStateEl.classList.add('is-valid');
                    setTimeout(() => physicalStateEl.classList.remove('is-valid'), 2000);
                }

                const mixologyFunctionEl = document.getElementById(prefix + 'MixologyFunction');
                if (mixologyFunctionEl && profile.mixology_function) {
                    mixologyFunctionEl.value = profile.mixology_function;
                    mixologyFunctionEl.classList.add('is-valid');
                    setTimeout(() => mixologyFunctionEl.classList.remove('is-valid'), 2000);
                    toggleCoffeeFields(prefix);
                }

                // Coffee fields populator
                const coffeeFields = {
                    'RoastLevel': profile.roast_level || 'MEDIUM',
                    'BodyIntensity': profile.body_intensity || 3,
                    'AcidityScore': profile.acidity_score || 3,
                    'BitternessScore': profile.bitterness_score || 3,
                    'FlavorNotes': profile.flavor_notes || '',
                    'Origin': profile.origin || '',
                    'Roaster': profile.roaster || '',
                    'Process': profile.process || ''
                };
                for (const [suffix, value] of Object.entries(coffeeFields)) {
                    const el = document.getElementById(prefix + suffix);
                    if (el) {
                        if (suffix === 'RoastLevel') {
                            el.value = String(value || 'MEDIUM').toUpperCase();
                        } else if (suffix === 'Process') {
                            el.value = String(value || '').toLowerCase();
                        } else if (suffix === 'FlavorNotes' || suffix === 'Origin' || suffix === 'Roaster') {
                            el.value = value !== null && value !== undefined ? String(value) : '';
                        } else {
                            const parsedVal = parseFloat(value);
                            el.value = isNaN(parsedVal) ? 3 : Math.round(parsedVal);
                        }
                        el.classList.add('is-valid');
                        setTimeout(() => el.classList.remove('is-valid'), 2000);
                    }
                }
                const decafEl = document.getElementById(prefix + 'IsDecaf');
                if (decafEl && profile.is_decaf !== undefined) {
                    decafEl.checked = profile.is_decaf === true || profile.is_decaf === 'true';
                    decafEl.classList.add('is-valid');
                    setTimeout(() => decafEl.classList.remove('is-valid'), 2000);
                }

                if (profile.compatible_systems) {
                    let systems = [];
                    if (Array.isArray(profile.compatible_systems)) {
                        systems = profile.compatible_systems
                            .filter(s => s !== null && s !== undefined)
                            .map(s => String(s).trim().toUpperCase());
                    } else if (typeof profile.compatible_systems === 'string') {
                        systems = profile.compatible_systems.split(',').map(s => s.trim().toUpperCase());
                    } else {
                        systems = String(profile.compatible_systems).split(',').map(s => s.trim().toUpperCase());
                    }
                    const sodaChk = document.getElementById(prefix + 'SysSoda');
                    const coffeeChk = document.getElementById(prefix + 'SysCoffee');
                    const slushieChk = document.getElementById(prefix + 'SysSlushie');
                    if (sodaChk) sodaChk.checked = systems.includes('SODA');
                    if (coffeeChk) coffeeChk.checked = systems.includes('COFFEE');
                    if (slushieChk) slushieChk.checked = systems.includes('SLUSHIE');
                }

                const aiNotesEl = document.getElementById(prefix + 'AINotes');
                if (aiNotesEl && profile.ai_notes) {
                    aiNotesEl.value = profile.ai_notes;
                    aiNotesEl.classList.add('is-valid');
                    setTimeout(() => aiNotesEl.classList.remove('is-valid'), 2000);
                }



                btn.innerHTML = '<i class="bi bi-check-lg"></i> Synced';
                btn.classList.replace('btn-outline-experimental', 'btn-success');
            } else {
                alert("Analysis Error: " + data.error);
            }
        } catch (err) {
            console.error('[synthesizeProfile] Caught exception:', err);
            alert("Comms Failure: Could not reach assistant substrate.\n\nSee browser console (F12) for details.");
        } finally {
            setTimeout(() => {
                btn.disabled = false;
                btn.innerHTML = originalHtml;
                btn.classList.remove('btn-success');
                btn.classList.add('btn-outline-experimental');
            }, 2000);
        }
    }

    function pollAnalysisTask(taskId, onProgress, onSuccess, onFailure) {
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

    // 6. Bulk Analysis Logic
    const btnBulkAnalyze = document.getElementById('btnBulkAnalyze');
    if (btnBulkAnalyze) {
        btnBulkAnalyze.addEventListener('click', function() {
            if (!confirm("Initiate Bulk Chemical Synthesis? This will analyze all reagents in your inventory to capture any updates. This may take 10-30 seconds.")) return;
            
            const originalHtml = btnBulkAnalyze.innerHTML;
            btnBulkAnalyze.disabled = true;
            btnBulkAnalyze.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> INITIALIZING...';
            
            fetch('/api/ai/bulk-analyze/', {
                method: 'POST',
                headers: { 'X-CSRFToken': window.CSRF_TOKEN }
            })
            .then(r => {
                if (r.status === 202) {
                    return r.json().then(data => {
                        pollAnalysisTask(data.task_id,
                            (progress) => {
                                btnBulkAnalyze.innerHTML = `<span class="spinner-border spinner-border-sm me-1"></span> ANALYZING (${progress}%)...`;
                            },
                            (result) => {
                                btnBulkAnalyze.innerHTML = '<i class="bi bi-check-all me-1"></i> SYNCED';
                                btnBulkAnalyze.classList.replace('btn-outline-experimental', 'btn-success');
                                setTimeout(() => location.reload(), 1500);
                            },
                            (errorMsg) => {
                                btnBulkAnalyze.disabled = false;
                                btnBulkAnalyze.innerHTML = originalHtml;
                                alert("Analysis Failed: " + errorMsg);
                            }
                        );
                    });
                } else {
                    return r.json().then(data => {
                        btnBulkAnalyze.disabled = false;
                        btnBulkAnalyze.innerHTML = originalHtml;
                        alert("Analysis Failed: " + (data.error || "Internal Error"));
                    });
                }
            })
            .catch(err => {
                btnBulkAnalyze.disabled = false;
                btnBulkAnalyze.innerHTML = originalHtml;
                alert("Signal Loss: Laboratory Substrate is unreachable.");
            });
        });
    }