---
name: IMDb Intelligence
description: Natural Language Cinema Search & Parquet Analytics
colors:
  primary: "#F5C518"
  primary-hover: "#FFD034"
  bg-deep: "#07090E"
  bg-base: "#0B0E14"
  bg-surface: "#11151E"
  bg-surface-elevated: "#171C28"
  text-primary: "#F3F4F6"
  text-secondary: "#9CA3AF"
  text-muted: "#6B7280"
  accent-emerald: "#10B981"
  accent-cyan: "#06B6D4"
  accent-ruby: "#EF4444"
typography:
  display:
    fontFamily: "Outfit, -apple-system, sans-serif"
    fontSize: "2.75rem"
    fontWeight: 800
    lineHeight: 1.15
    letterSpacing: "-0.03em"
  headline:
    fontFamily: "Outfit, -apple-system, sans-serif"
    fontSize: "1.35rem"
    fontWeight: 700
    lineHeight: 1.3
    letterSpacing: "-0.02em"
  title:
    fontFamily: "Outfit, -apple-system, sans-serif"
    fontSize: "1.1rem"
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: "-0.01em"
  body:
    fontFamily: "Outfit, -apple-system, sans-serif"
    fontSize: "0.95rem"
    fontWeight: 400
    lineHeight: 1.6
    letterSpacing: "normal"
  label:
    fontFamily: "JetBrains Mono, monospace"
    fontSize: "0.8rem"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "0.04em"
rounded:
  sm: "6px"
  md: "10px"
  lg: "16px"
  full: "999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "24px"
  xl: "32px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "#0B0E14"
    rounded: "{rounded.md}"
    padding: "10px 22px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
---

# Design System: IMDb Intelligence

## Overview

**Creative North Star: "Projectionist's Digital Command Console"**

IMDb Intelligence is designed as an elite, high-precision cinematic console. It drops users into a dark screening room environment with deep OLED obsidian foundations, glowing amber beam accents reminiscent of movie projectors, and crisp emerald/cyan telemetry tags for cloud execution metrics.

The experience strips away 2000s-era table clunkiness and replaces it with an ultra-responsive natural language aperture, silky-smooth filter chips, real-time SQL execution inspection, and contextual AI synopsis triggers.

**Key Characteristics:**
- Deep obsidian backdrop (`#07090E`) with atmospheric gold ambient backlight aura.
- Signature IMDb Gold/Amber (`#F5C518`) used purposefully for primary actions, rating stars, and focus indicators.
- High-contrast typography pairing `Outfit` for UI/Display and `JetBrains Mono` for SQL code and telemetry badges.
- Glassmorphic elevation with backdrop filters on headers, search console, and modal dialogs.

## Colors

The palette is tuned for high-contrast dark room viewing, with rich blacks, slate glass surfaces, and warm luminous amber projector lighting.

### Primary
- **IMDb Luminous Amber** (`#F5C518`): Used for primary action buttons, key brand elements, rating stars, and glowing focus borders.

### Secondary
- **Cloud Emerald** (`#10B981`): Used for live cloud status, successful query state indicators, and security confirmations.
- **Electric Cyan** (`#06B6D4`): Used for genre pills, radar rings, and filter badge accents.

### Tertiary
- **Ruby Alert** (`#EF4444`): Used strictly for error messages, clear credentials action, and failed query notices.

### Neutral
- **Obsidian Deep** (`#07090E`): Base canvas background.
- **Slate Glass Surface** (`#11151E`): Card containers, search shell, and modal surfaces.
- **Elevated Slate** (`#171C28`): Hover surfaces, table header rows, and dropdown inputs.
- **Pure Crisp Light** (`#F3F4F6`): High-legibility primary text (contrast > 12:1 against base).
- **Secondary Gray** (`#9CA3AF`): Metadata, column subtitles, and descriptions.

### Named Rules
**The Projectionist's Contrast Rule.** All body text maintains at least 4.5:1 contrast against dark backgrounds; primary headlines maintain > 10:1 contrast. Amber accent glow is reserved strictly for active elements and focus states.

## Typography

**Display & Body Font:** Outfit (fallback: `-apple-system, BlinkMacSystemFont, sans-serif`)
**Code & Data Font:** JetBrains Mono (fallback: `SFMono-Regular, Menlo, Consolas, monospace`)

**Character:** Modern geometric sans-serif with friendly curves and high clarity paired with an ultra-clean developer monospace face for data metrics.

### Hierarchy
- **Display** (800 weight, 2.75rem, line-height 1.15): Hero banner headline.
- **Headline** (700 weight, 1.35rem, line-height 1.3): Modal title and AI synopsis title.
- **Title** (600 weight, 1.1rem, line-height 1.4): Table headers and card group headers.
- **Body** (400 weight, 0.95rem, line-height 1.6): Synopsis content, search suggestions, and error copy.
- **Label / Data** (600 weight, 0.8rem, JetBrains Mono): Row counts, DuckDB latency, SQL code, and year tags.

## Layout

- **Spatial Model:** 12-column responsive grid with max width of 1400px, centering the core search console in a focused 820px aperture.
- **Spacing Rhythm:** Multiples of 8px (`8px`, `16px`, `24px`, `32px`, `48px`). Headings feature double the margin-top relative to margin-bottom for clear section anchoring.

## Elevation & Depth

Surfaces rely on subtle tonal gradation (`#07090E` -> `#11151E` -> `#171C28`) paired with 1px subtle borders (`rgba(255, 255, 255, 0.07)`) and deep soft offset shadows (`0 8px 24px rgba(0, 0, 0, 0.55)`).

### Shadow Vocabulary
- **Subtle Surface** (`0 2px 8px rgba(0, 0, 0, 0.4)`): Buttons, badges, and chips.
- **Card Elevation** (`0 8px 24px rgba(0, 0, 0, 0.55)`): Search console, data table, and filter card.
- **Modal Float** (`0 16px 40px rgba(0, 0, 0, 0.7)`): Settings dialog and AI synopsis dialog.
- **Amber Glow** (`0 0 30px rgba(245, 197, 24, 0.18)`): Active focus ring on search bar and primary buttons.

## Shapes

- **Corner Language:** 16px radius on primary containers and search shell; 10px on buttons, inputs, and modal headers; 6px on data badges and code pills; 999px pill radius on suggestion chips.

## Components

### Search Aperture Shell
- **Shape:** 16px rounded pill container with integrated leading magnifying glass, clear button (`Esc`), keyboard trigger badge (`/`), and gold execution button.
- **Focus:** Luminous amber border with soft 30px ambient glow.

### Data Table & DataTables
- **Shape:** 16px rounded card with dark header (`#0E121A`), 1px subtle divider lines, and hover highlighting (`rgba(255, 255, 255, 0.02)`).
- **Cells:** IMDb links rendered with external badge; ratings rendered as gold star badges; genres rendered as cyan pills; AI Synopsis triggered via gold sparkle icon button.

### SQL Terminal Drawer
- **Shape:** 12px rounded dark slate box (`#080A0F`) with macOS-styled red/yellow/green indicator dots, copy button, and syntax highlighted green/cyan monospace text.

### AI Synopsis Modal
- **Shape:** 18px rounded glass dialog with backdrop blur (20px), gold sparkle header, animated projector loader, and formatted prose typography.

## Do's and Don'ts

### Do:
- **Do** maintain the cinematic dark aesthetic with obsidian base and luminous amber accents.
- **Do** display real-time query metrics (row count, latency) in clean monospace badges.
- **Do** format table columns with domain-specific badges (stars for ratings, pills for genres, external links for IDs).
- **Do** provide smooth keyboard shortcuts (`/` to search, `Esc` to clear).

### Don't:
- **Don't** reintroduce light backgrounds or harsh generic Bootstrap blue gradients.
- **Don't** use bounce or elastic animation easing.
- **Don't** show unformatted raw JSON or unstyled SQL text.
- **Don't** hide error states; always provide actionable suggestions and a retry button.
