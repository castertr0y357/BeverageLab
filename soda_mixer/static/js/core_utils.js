/**
 * Core Utilities for BeverageLab
 * 
 * Provides shared helper functions to unify mode string comparisons
 * and standard validations across the frontend.
 */

function isCryoMode(modeStr) {
    if (!modeStr) return false;
    const m = modeStr.toUpperCase();
    return m === 'CRYO' || m === 'SLUSHIE';
}

function isCoffeeMode(modeStr) {
    if (!modeStr) return false;
    return modeStr.toUpperCase() === 'COFFEE';
}

function isSodaMode(modeStr) {
    if (!modeStr) return false;
    return modeStr.toUpperCase() === 'SODA';
}

// Export for module usage if needed, otherwise rely on global scope inclusion
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { isCryoMode, isCoffeeMode, isSodaMode };
}
