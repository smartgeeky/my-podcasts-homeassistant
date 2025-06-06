// Internationalization (i18n) system for My Podcasts
class I18n {
    constructor() {
        this.currentLanguage = 'en'; // Default language
        this.translations = {};
        this.fallbackLanguage = 'en';
    }

    // Initialize language system
    async init() {
        // Get saved language from localStorage or use default
        this.currentLanguage = localStorage.getItem('podcast_language') || 'en';
        
        // Load the language file
        await this.loadLanguage(this.currentLanguage);
        
        // Apply translations to current page
        this.applyTranslations();
    }

    // Load language JSON file
    async loadLanguage(lang) {
        try {
            const response = await fetch(`static/lang/${lang}.json`);
            if (!response.ok) {
                throw new Error(`Failed to load language file: ${lang}.json`);
            }
            
            this.translations = await response.json();
            this.currentLanguage = lang;
            
            // Save language preference
            localStorage.setItem('podcast_language', lang);
            
            console.log(`Language loaded: ${lang}`);
            return true;
        } catch (error) {
            console.error(`Error loading language ${lang}:`, error);
            
            // If it's not the fallback language, try to load fallback
            if (lang !== this.fallbackLanguage) {
                console.log(`Falling back to ${this.fallbackLanguage}`);
                return await this.loadLanguage(this.fallbackLanguage);
            }
            return false;
        }
    }

    // Get translation for a key (supports nested keys like "header.title")
    t(key, params = {}) {
        const keys = key.split('.');
        let value = this.translations;
        
        // Navigate through nested object
        for (const k of keys) {
            if (value && typeof value === 'object' && k in value) {
                value = value[k];
            } else {
                console.warn(`Translation key not found: ${key}`);
                return key; // Return the key if translation not found
            }
        }
        
        // Replace parameters in string like {time}, {added}, etc.
        if (typeof value === 'string' && Object.keys(params).length > 0) {
            return value.replace(/\{(\w+)\}/g, (match, param) => {
                return params[param] !== undefined ? params[param] : match;
            });
        }
        
        return value;
    }

    // Apply translations to current page
    applyTranslations() {
        // Find all elements with data-i18n attribute
        const elements = document.querySelectorAll('[data-i18n]');
        
        elements.forEach(element => {
            const key = element.getAttribute('data-i18n');
            const translation = this.t(key);
            
            // Apply translation based on element type
            if (element.tagName === 'INPUT') {
                if (element.type === 'submit' || element.type === 'button') {
                    element.value = translation;
                } else {
                    element.placeholder = translation;
                }
            } else if (element.tagName === 'OPTION') {
                element.textContent = translation;
            } else {
                element.textContent = translation;
            }
        });

        // Find all elements with data-i18n-placeholder attribute
        const placeholderElements = document.querySelectorAll('[data-i18n-placeholder]');
        placeholderElements.forEach(element => {
            const key = element.getAttribute('data-i18n-placeholder');
            element.placeholder = this.t(key);
        });

        // Find all elements with data-i18n-title attribute (for tooltips)
        const titleElements = document.querySelectorAll('[data-i18n-title]');
        titleElements.forEach(element => {
            const key = element.getAttribute('data-i18n-title');
            element.title = this.t(key);
        });
    }

    // Change language and reload translations
    async changeLanguage(lang) {
        if (lang === this.currentLanguage) {
            return; // Already using this language
        }
        
        const success = await this.loadLanguage(lang);
        if (success) {
            this.applyTranslations();
            
            // Trigger custom event for other parts of the app
            window.dispatchEvent(new CustomEvent('languageChanged', {
                detail: { language: lang }
            }));
        }
    }

    // Get current language
    getCurrentLanguage() {
        return this.currentLanguage;
    }

    // Get available languages
    getAvailableLanguages() {
        return [
            { code: 'en', name: this.t('settings.english') },
            { code: 'sl', name: this.t('settings.slovenian') }
        ];
    }

    // Helper method for showing translated messages (like alerts, toasts)
    showMessage(key, params = {}) {
        return this.t(`messages.${key}`, params);
    }

    // Helper method for API error messages
    showError(key, params = {}) {
        return this.t(`api_errors.${key}`, params);
    }
}

// Create global instance
window.i18n = new I18n();

// Initialize when DOM is loaded
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        window.i18n.init();
    });
} else {
    // DOM already loaded
    window.i18n.init();
}

// Utility function for quick access (global shortcut)
window.t = function(key, params = {}) {
    return window.i18n.t(key, params);
};