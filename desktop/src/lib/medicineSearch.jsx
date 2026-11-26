// Medicine search shared by the prescription form and the billing counter.

function matchScore(medicine, query) {
  const fields = [medicine.name, medicine.salt, medicine.generic_name, medicine.manufacturer, medicine.sku, medicine.strength, medicine.form, medicine.barcode].map(
    (value) => (value || "").toLowerCase(),
  );
  const starts = fields.findIndex((value) => value.startsWith(query));
  if (starts >= 0) return starts;
  const contains = fields.findIndex((value) => value.includes(query));
  if (contains >= 0) return 10 + contains;
  return 99;
}

export function suggestionsFor(medicines, query) {
  const needle = query.trim().toLowerCase();
  if (!needle) return [];
  return medicines
    .map((medicine) => ({ medicine, score: matchScore(medicine, needle) }))
    .filter((row) => row.score < 99)
    .sort((a, b) => a.score - b.score || a.medicine.name.localeCompare(b.medicine.name))
    .slice(0, 8)
    .map((row) => row.medicine);
}

export function Highlight({ text, query }) {
  const value = text || "";
  const needle = query.trim();
  const index = needle ? value.toLowerCase().indexOf(needle.toLowerCase()) : -1;
  if (index < 0) return value;
  return (
    <>
      {value.slice(0, index)}
      <mark>{value.slice(index, index + needle.length)}</mark>
      {value.slice(index + needle.length)}
    </>
  );
}

export function findByBarcode(medicines, code) {
  const needle = code.trim();
  if (!needle) return null;
  return medicines.find((medicine) => medicine.barcode && medicine.barcode === needle) || null;
}
