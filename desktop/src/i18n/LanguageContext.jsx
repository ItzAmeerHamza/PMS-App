import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { LANGUAGES, LOCALES, catalogs } from "./catalog";
import { setFormatLocale } from "../lib/format";

const STORAGE_KEY = "pharmacare_lang";
const LanguageContext = createContext(null);

function lookup(language, key) {
  return catalogs[language]?.[key] ?? catalogs.en[key] ?? key;
}

function fill(template, vars) {
  if (!vars) return template;
  return Object.entries(vars).reduce((text, [name, value]) => text.replaceAll(`{${name}}`, value ?? ""), template);
}

function readLanguage() {
  const stored = localStorage.getItem(STORAGE_KEY);
  return catalogs[stored] ? stored : "en";
}

export function LanguageProvider({ children }) {
  const [language, setLanguage] = useState(readLanguage);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, language);
  }, [language]);

  const urdu = language === "ur";
  document.documentElement.lang = urdu ? "ur" : "en";
  document.documentElement.dir = urdu ? "rtl" : "ltr";

  const value = useMemo(() => {
    setFormatLocale(LOCALES[language]);
    function t(key, vars) {
      return fill(lookup(language, key), vars);
    }
    function named(group, raw) {
      if (!raw) return t(`${group}.unspecified`);
      const key = `${group}.${String(raw).toLowerCase()}`;
      const text = t(key);
      return text === key ? raw : text;
    }
    return { language, setLanguage, t, named };
  }, [language]);

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useI18n() {
  return useContext(LanguageContext);
}

export function LanguageSwitcher({ tone = "dark" }) {
  const { language, setLanguage, t } = useI18n();
  return (
    <div className={`lang-switch ${tone}`} role="group" aria-label={t("common.language")}>
      {LANGUAGES.map((option) => (
        <button
          key={option.id}
          type="button"
          className={language === option.id ? "active" : ""}
          onClick={() => setLanguage(option.id)}
          aria-pressed={language === option.id}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

export function withName(text, name) {
  const [before, after] = String(text).split("{name}");
  return (
    <>
      {before}
      <strong>{name}</strong>
      {after}
    </>
  );
}
