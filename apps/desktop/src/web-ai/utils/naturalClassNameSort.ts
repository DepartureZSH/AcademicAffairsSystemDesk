// @ts-nocheck -- upstream source
type NaturalClassNamePart =
  | { kind: "number"; value: number; source: "arabic" | "chinese" }
  | { kind: "text"; value: string };

const chineseDigitValues: Record<string, number> = {
  零: 0,
  〇: 0,
  一: 1,
  二: 2,
  两: 2,
  三: 3,
  四: 4,
  五: 5,
  六: 6,
  七: 7,
  八: 8,
  九: 9,
};

const chineseUnitValues: Record<string, number> = {
  十: 10,
  百: 100,
  千: 1000,
};

const classNameCollator = new Intl.Collator("zh-Hans-CN", {
  numeric: true,
  sensitivity: "base",
});

function chineseNumeralValue(value: string) {
  if (!/[十百千万]/.test(value)) {
    const digits = Array.from(value).map((character) => chineseDigitValues[character]);
    return digits.every((digit) => digit !== undefined)
      ? Number(digits.join(""))
      : Number.NaN;
  }

  let total = 0;
  let section = 0;
  let digit = 0;
  for (const character of value) {
    if (character in chineseDigitValues) {
      digit = chineseDigitValues[character];
      continue;
    }
    if (character === "万") {
      section += digit;
      total += section * 10000;
      section = 0;
      digit = 0;
      continue;
    }
    const unit = chineseUnitValues[character];
    if (unit) {
      section += (digit || 1) * unit;
      digit = 0;
    }
  }
  return total + section + digit;
}

function normalizeFullWidthDigits(value: string) {
  return value.replace(/[０-９]/g, (character) =>
    String(character.charCodeAt(0) - "０".charCodeAt(0)),
  );
}

function naturalClassNameParts(value: unknown): NaturalClassNamePart[] {
  const normalized = normalizeFullWidthDigits(String(value || "").trim());
  const parts: NaturalClassNamePart[] = [];
  const numberPattern = /\d+|[零〇一二两三四五六七八九十百千万]+/g;
  let start = 0;
  for (const match of normalized.matchAll(numberPattern)) {
    const index = match.index || 0;
    if (index > start) {
      parts.push({ kind: "text", value: normalized.slice(start, index) });
    }
    const token = match[0];
    const number = /^\d+$/.test(token) ? Number(token) : chineseNumeralValue(token);
    if (Number.isFinite(number)) {
      parts.push({ kind: "number", value: number, source: /^\d+$/.test(token) ? "arabic" : "chinese" });
    } else {
      parts.push({ kind: "text", value: token });
    }
    start = index + token.length;
  }
  if (start < normalized.length) {
    parts.push({ kind: "text", value: normalized.slice(start) });
  }
  return parts;
}

function compareNaturalParts(left: unknown, right: unknown, chineseNumberFirst: boolean) {
  const leftParts = naturalClassNameParts(left);
  const rightParts = naturalClassNameParts(right);
  const length = Math.max(leftParts.length, rightParts.length);
  for (let index = 0; index < length; index += 1) {
    const leftPart = leftParts[index];
    const rightPart = rightParts[index];
    if (!leftPart || !rightPart) return leftParts.length - rightParts.length;
    if (leftPart.kind === "number" && rightPart.kind === "number") {
      const difference = leftPart.value - rightPart.value;
      if (difference) return difference;
      if (chineseNumberFirst && leftPart.source !== rightPart.source) {
        return leftPart.source === "chinese" ? -1 : 1;
      }
      continue;
    }
    if (leftPart.kind === "text" && rightPart.kind === "text") {
      const difference = classNameCollator.compare(leftPart.value, rightPart.value);
      if (difference) return difference;
      continue;
    }
    return leftPart.kind === "number" ? -1 : 1;
  }
  return 0;
}

export function compareNaturalClassNames(left: unknown, right: unknown) {
  return compareNaturalParts(left, right, false);
}

export function compareNaturalRoomNames(left: unknown, right: unknown) {
  return compareNaturalParts(left, right, true);
}
