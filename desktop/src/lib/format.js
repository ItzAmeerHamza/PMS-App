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

// The API stores timestamps in UTC; SQLite returns them without an offset, so read those as UTC.
export function parseDate(value) {
  if (value instanceof Date) return value;
  if (typeof value === "string" && value.includes("T") && !/(Z|[+-]\d\d:?\d\d)$/.test(value)) {
    return new Date(`${value}Z`);
  }
  return new Date(value);
}

export function formatDate(value) {
  if (!value) return "—";
  return parseDate(value).toLocaleDateString(activeLocale);
}

export function formatDateTime(value) {
  if (!value) return "—";
  return parseDate(value).toLocaleString(activeLocale);
}

export function startOfDay(date = new Date()) {
  const day = new Date(date);
  day.setHours(0, 0, 0, 0);
  return day;
}

export function addDays(date, days) {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

export function toInputDate(date) {
  const pad = (n) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

export function fromInputDate(value) {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year, month - 1, day);
}
