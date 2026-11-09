// Number and date formats from DesignSystem.md section 5.

const integer = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const thaiDate = new Intl.DateTimeFormat("th-TH-u-ca-buddhist", {
  day: "numeric",
  month: "short",
  year: "numeric",
});

/** "฿45,000" */
export const baht = (value) => `฿${integer.format(value)}`;

/** "฿35,000 – ฿55,000" */
export const bahtRange = (min, max) => `${baht(min)} – ${baht(max)}`;

/** "1,284" */
export const num = (value) => integer.format(value);

/** "72%" (match % is always an integer) */
export const pct = (ratio) => `${Math.round(ratio * 100)}%`;

/** "3 พ.ย. 2569" from an ISO date */
export const dateTh = (iso) => thaiDate.format(new Date(iso));
