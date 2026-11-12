let activeLocale;

export function setFormatLocale(locale) {
  activeLocale = locale;
}

const pkr = new Intl.NumberFormat("en-PK", {
  style: "currency",
  currency: "PKR",
  currencyDisplay: "code",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export function money(value) {
  return pkr.format(Number(value || 0));
}

export function fullName(person) {
  if (!person) return "";
  return `${person.first_name} ${person.last_name}`.trim();
}

export function formatDate(value) {
  if (!value) return "—";
  return new Date(value).toLocaleDateString(activeLocale);
}

export function formatDateTime(value) {
  if (!value) return "—";
  return new Date(value).toLocaleString(activeLocale);
}
