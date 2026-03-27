# Design System Specification: Editorial Sophistication

## 1. Overview & Creative North Star
**The Creative North Star: "The Curated Gallery"**

This design system rejects the "boxed-in" nature of traditional web templates in favor of an editorial, high-end gallery aesthetic. By leveraging a palette of warm neutrals and deep vinous tones, we create an environment that feels both authoritative and inviting. 

We break the "template" look through **Intentional Asymmetry**. Instead of rigid, centered grids, we utilize the Spacing Scale to create "breathing pockets"—large areas of whitespace that guide the eye toward high-contrast typography. Elements should feel layered rather than placed, using overlapping images and text to create a sense of tactile depth.

---

## 2. Colors & Tonal Depth

The palette is rooted in the interplay between the light, airy `surface` (#fff8f7) and the deep, intellectual `secondary` (Eggplant). 

### The "No-Line" Rule
**Explicit Instruction:** Designers are prohibited from using 1px solid borders for sectioning or containment. Boundaries must be defined solely through background color shifts or tonal transitions. To separate a feature section from the hero, transition from `surface` to `surface-container-low`.

### Surface Hierarchy & Nesting
Treat the UI as a series of physical layers, like stacked sheets of fine vellum.
*   **Base:** `surface` (#fff8f7)
*   **Nesting:** Place a `surface-container-lowest` card on a `surface-container-low` section to create a soft, natural lift.
*   **The "Glass & Gradient" Rule:** For floating navigation or high-impact overlays, use Glassmorphism. Apply `surface` at 70% opacity with a `24px` backdrop-blur. 
*   **Signature Textures:** Use subtle linear gradients for primary CTAs, transitioning from `primary` (#864f51) to `primary-container` (#a26769) at a 135° angle. This adds a "soul" to the component that flat hex codes cannot achieve.

---

## 3. Typography

The system uses a pairing of **Manrope** (Display/Headlines) for its geometric modernism and **Work Sans** (Body/Labels) for its exceptional legibility and professional warmth.

*   **Display (Manrope):** Use `display-lg` (3.5rem) with tight letter-spacing (-0.02em) for hero statements. This conveys a "Premium Editorial" voice.
*   **Headlines (Manrope):** `headline-md` (1.75rem) should be used for section titles, always paired with a `secondary` color (#8d4861) to anchor the page.
*   **Body (Work Sans):** `body-lg` (1rem) is our workhorse. Ensure a line-height of 1.6 to maintain the "clean and balanced" feel requested.
*   **Labels (Work Sans):** Use `label-md` in uppercase with `0.05em` letter-spacing for category tags or small metadata to provide a technical, professional contrast to the fluid headlines.

---

## 4. Elevation & Depth

We achieve hierarchy through **Tonal Layering** rather than structural lines or heavy drop shadows.

*   **The Layering Principle:** Depth is "stacked." A `surface-container-highest` element represents the most interactive or urgent layer, while `surface-dim` represents the background environment.
*   **Ambient Shadows:** When an element must "float" (e.g., a dropdown or modal), use a shadow with a `40px` blur and `4%` opacity. The shadow color must be a tinted version of `on-surface` (#22191a), never pure black.
*   **The "Ghost Border" Fallback:** If accessibility requires a container definition, use the `outline-variant` token at **15% opacity**. High-contrast, 100% opaque borders are strictly forbidden as they clutter the visual field.

---

## 5. Components

### Buttons
*   **Primary:** Gradient fill (`primary` to `primary-container`). Roundedness: `md` (0.375rem). Text: `label-md` in `on-primary`.
*   **Secondary:** Ghost style. No background, but a `Ghost Border` (outline-variant @ 20%). On hover, fill with `surface-container-high`.
*   **Tertiary:** Purely typographic with a `2px` underline using the `tertiary` color.

### Modern Cards & Grids
*   **Structure:** No borders. Use `surface-container-low` for the card body. 
*   **Spacing:** Use `spacing-6` (2rem) for internal padding to ensure the "whitespace" requirement is met.
*   **Interaction:** On hover, the card should transition its background to `surface-container-highest` and scale by 1.02x. Do not use shadows for hover states; use color shifts.

### Input Fields
*   **Styling:** Fields should be "Bottom-Line Only" or "Soft Surface." We prefer a soft surface: `surface-container-low` with a `md` corner radius.
*   **Focus State:** The background shifts to `surface-container-highest` with a `2px` bottom-bar of `primary`.

### Navigation (Editorial Style)
*   **Additional Component:** The **"Mega-Breadcrumb."** Instead of a standard small breadcrumb, use `title-lg` typography for page location to give the user a strong sense of place and professional hierarchy.

---

## 6. Do’s and Don’ts

### Do:
*   **Do** use asymmetrical margins (e.g., `spacing-12` on the left, `spacing-24` on the right) for hero sections to create an editorial feel.
*   **Do** allow images to bleed off the edge of the container or overlap into the next section.
*   **Do** use the `secondary` (Eggplant) color sparingly as an "anchor" for key calls to action or footer backgrounds.

### Don’t:
*   **Don’t** use 1px dividers between list items. Use `spacing-4` (1.4rem) of vertical whitespace instead.
*   **Don’t** use pure black (#000000) for text. Always use `on-surface` (#22191a) to maintain the "Alabaster/Marsala" warmth.
*   **Don’t** use "Perfectly Round" (9999px) buttons unless they are icon-only. Stick to the `md` or `lg` scale for a more professional, architectural look.