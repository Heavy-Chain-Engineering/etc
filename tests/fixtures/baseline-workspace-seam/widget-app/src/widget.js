// The remote frontend the host loads. Reads the SAME recipe table (the seam).
export function renderWidget(recipe) {
  return `<div class="widget">${recipe.title}</div>`;
}
