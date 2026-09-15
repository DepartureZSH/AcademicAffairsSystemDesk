import type { Worksheet } from "exceljs";

export function fitWorksheetToPrintedPage(worksheet: Worksheet, orientation: "landscape" | "portrait") {
  const rowCount = worksheet.rowCount;
  const columnCount = worksheet.columnCount;
  if (!rowCount || !columnCount) return;
  const margin = 0.25;
  const width = (orientation === "landscape" ? 297 : 210) * 72 / 25.4 - margin * 144;
  const height = (orientation === "landscape" ? 210 : 297) * 72 / 25.4 - margin * 144;
  const heights = Array.from({ length: rowCount }, (_, i) => worksheet.getRow(i + 1).height || 28.5);
  const totalHeight = heights.reduce((sum, value) => sum + value, 0);
  // Leave a small tolerance for printer metrics and Excel's column-width rounding.
  const targetHeight = height * 0.98;
  const scale = Math.min(1, targetHeight / totalHeight);
  const rowExpansion = Math.max(1, targetHeight / totalHeight);
  heights.forEach((value, i) => { worksheet.getRow(i + 1).height = Math.min(409, value * rowExpansion); });
  const widths = Array.from({ length: columnCount }, (_, i) => worksheet.getColumn(i + 1).width || 13);
  const totalWidth = widths.reduce((sum, value) => sum + value, 0);
  widths.forEach((value, i) => {
    // Excel's default font uses approximately 7 pixels per character, plus 5 pixels padding.
    const pixels = width * 0.98 / scale * 96 / 72 * value / totalWidth;
    worksheet.getColumn(i + 1).width = Math.min(255, Math.max(1, (pixels - 5) / 7));
  });
  Object.assign(worksheet.pageSetup, {
    paperSize: 9, orientation, fitToPage: true, fitToWidth: 1, fitToHeight: 1,
    horizontalCentered: true, verticalCentered: true,
    printArea: `A1:${worksheet.getCell(rowCount, columnCount).address}`,
    margins: { left: margin, right: margin, top: margin, bottom: margin, header: 0, footer: 0 },
  });
}
