const SVG_NS = "http://www.w3.org/2000/svg";

function svgEl(tag, attrs) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    el.setAttribute(key, value);
  }
  return el;
}

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function makeTooltip(container) {
  const tooltip = document.createElement("div");
  tooltip.className = "chart-tooltip";
  tooltip.hidden = true;
  container.appendChild(tooltip);
  return tooltip;
}

function showTooltip(tooltip, container, x, y, lines) {
  tooltip.innerHTML = "";
  for (const line of lines) {
    const row = document.createElement("div");
    if (line.strong) {
      const strong = document.createElement("strong");
      strong.textContent = line.strong;
      row.appendChild(strong);
    }
    if (line.text) {
      const span = document.createElement("span");
      span.textContent = line.text;
      row.appendChild(span);
    }
    tooltip.appendChild(row);
  }
  tooltip.hidden = false;

  const containerRect = container.getBoundingClientRect();
  let left = x + 12;
  let top = y - 12;
  const tooltipRect = tooltip.getBoundingClientRect();
  if (left + tooltipRect.width > containerRect.width) {
    left = x - tooltipRect.width - 12;
  }
  if (top < 0) top = y + 12;
  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${top}px`;
}

function hideTooltip(tooltip) {
  tooltip.hidden = true;
}

/**
 * Line chart of discount_pct over time - a step-like line since prices only
 * change on event dates, not daily. Y axis fixed 0-100 (a percentage), X axis
 * scaled by actual date so gaps between discount events read as real time
 * gaps, not evenly-spaced ticks.
 */
function renderPriceHistoryChart(container, rows) {
  container.innerHTML = "";
  if (rows.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = "No price history recorded yet";
    container.appendChild(empty);
    return;
  }

  const width = 600;
  const height = 200;
  const padding = { top: 12, right: 12, bottom: 24, left: 32 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;

  const dates = rows.map((r) => new Date(r.date).getTime());
  const minDate = Math.min(...dates);
  const maxDate = Math.max(...dates);
  const dateSpan = Math.max(maxDate - minDate, 1);

  const x = (i) => padding.left + ((dates[i] - minDate) / dateSpan) * plotWidth;
  const y = (pct) => padding.top + plotHeight - (Math.min(pct, 100) / 100) * plotHeight;

  const svg = svgEl("svg", {
    viewBox: `0 0 ${width} ${height}`,
    class: "chart-svg",
    role: "img",
    "aria-label": "Discount percentage over time",
  });

  const gridline = cssVar("--gridline");
  const muted = cssVar("--axis-muted");
  const seriesColor = cssVar("--series-1");
  const surface = cssVar("--surface");

  for (const pct of [0, 25, 50, 75, 100]) {
    const gy = y(pct);
    svg.appendChild(
      svgEl("line", { x1: padding.left, y1: gy, x2: width - padding.right, y2: gy, stroke: gridline, "stroke-width": 1 })
    );
    const label = svgEl("text", { x: padding.left - 6, y: gy + 3, "text-anchor": "end", class: "chart-axis-label" });
    label.textContent = `${pct}%`;
    label.setAttribute("fill", muted);
    svg.appendChild(label);
  }

  const points = rows.map((r, i) => `${x(i)},${y(r.discount_pct || 0)}`).join(" ");
  svg.appendChild(
    svgEl("polyline", {
      points,
      fill: "none",
      stroke: seriesColor,
      "stroke-width": 2,
      "stroke-linejoin": "round",
      "stroke-linecap": "round",
    })
  );

  const lastIndex = rows.length - 1;
  svg.appendChild(
    svgEl("circle", {
      cx: x(lastIndex), cy: y(rows[lastIndex].discount_pct || 0), r: 5,
      fill: seriesColor, stroke: surface, "stroke-width": 2,
    })
  );

  const hitLayer = svgEl("rect", {
    x: padding.left, y: padding.top, width: plotWidth, height: plotHeight,
    fill: "transparent",
  });
  const crosshair = svgEl("line", {
    x1: 0, y1: padding.top, x2: 0, y2: height - padding.bottom,
    stroke: muted, "stroke-width": 1, visibility: "hidden",
  });
  svg.appendChild(crosshair);
  svg.appendChild(hitLayer);

  const tooltip = makeTooltip(container);

  hitLayer.addEventListener("pointermove", (event) => {
    const rect = svg.getBoundingClientRect();
    const relativeX = ((event.clientX - rect.left) / rect.width) * width;
    let nearest = 0;
    let nearestDist = Infinity;
    for (let i = 0; i < rows.length; i++) {
      const dist = Math.abs(x(i) - relativeX);
      if (dist < nearestDist) {
        nearestDist = dist;
        nearest = i;
      }
    }
    crosshair.setAttribute("x1", x(nearest));
    crosshair.setAttribute("x2", x(nearest));
    crosshair.setAttribute("visibility", "visible");

    const row = rows[nearest];
    const priceText = row.price === null || row.price === undefined ? "no price" : `$${Number(row.price).toFixed(2)}`;
    showTooltip(tooltip, container, event.clientX - rect.left, event.clientY - rect.top, [
      { strong: row.date },
      { text: `${priceText} · ${row.discount_pct || 0}% off` },
    ]);
  });
  hitLayer.addEventListener("pointerleave", () => {
    crosshair.setAttribute("visibility", "hidden");
    hideTooltip(tooltip);
  });

  container.appendChild(svg);
}

/**
 * Horizontal stacked bar - each segment's width is its already-weighted
 * contribution (0-100 scale, summing to the deal score). 2px surface gaps
 * between segments per the mark spec; each segment direct-labeled since
 * there are only 3 (aqua's the one categorical slot under 3:1 contrast on
 * light mode, so it always carries a visible text label, never color alone).
 */
function renderStackedBarChart(container, segments) {
  container.innerHTML = "";
  const total = segments.reduce((sum, s) => sum + Math.max(s.value, 0), 0);

  const bar = document.createElement("div");
  bar.className = "stacked-bar";
  const tooltip = makeTooltip(container);

  segments.forEach((segment, i) => {
    const widthPct = total > 0 ? (Math.max(segment.value, 0) / total) * 100 : 100 / segments.length;
    const piece = document.createElement("div");
    piece.className = "stacked-bar-segment";
    piece.style.width = `${widthPct}%`;
    piece.style.background = `var(--series-${i + 1})`;
    piece.tabIndex = 0;
    piece.addEventListener("pointermove", (event) => {
      const rect = container.getBoundingClientRect();
      showTooltip(tooltip, container, event.clientX - rect.left, event.clientY - rect.top, [
        { strong: `${segment.value.toFixed(1)} pts` },
        { text: segment.label },
      ]);
    });
    piece.addEventListener("pointerleave", () => hideTooltip(tooltip));
    bar.appendChild(piece);
  });
  container.appendChild(bar);

  const legend = document.createElement("div");
  legend.className = "chart-legend";
  segments.forEach((segment, i) => {
    const item = document.createElement("div");
    item.className = "chart-legend-item";
    const swatch = document.createElement("span");
    swatch.className = "chart-legend-swatch";
    swatch.style.background = `var(--series-${i + 1})`;
    const text = document.createElement("span");
    text.textContent = `${segment.label} (${segment.value.toFixed(1)})`;
    item.append(swatch, text);
    legend.appendChild(item);
  });
  container.appendChild(legend);
}

