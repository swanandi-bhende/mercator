# Design System Strategy: The Serene Monolith

## 1. Overview & Creative North Star
The Creative North Star for this design system is **"The Silent Authority."** 

This system rejects the frantic, cluttered layouts of the modern web in favor of an editorial, museum-like experience. We are not building a "template"; we are constructing a digital environment that breathes. By leveraging the interplay between the deep, obsidian-like `#101415` background and the ethereal sage tones, we create a sense of grounded luxury. 

To move beyond "standard" UI, this system utilizes **Intentional Asymmetry**. We break the rigid 12-column grid by allowing imagery to bleed off-canvas and using "The Power of the Void"—massive, calculated gaps of whitespace (using our `20` and `24` spacing tokens) to force focus onto singular, high-impact elements.

---

## 2. Colors: Tonal Depth & The "No-Line" Rule
Our palette is a study in atmospheric fog and deep water. We use color not as a decoration, but as a spatial tool.

### The "No-Line" Rule
**Explicit Instruction:** You are prohibited from using 1px solid borders for sectioning. Traditional dividers are a sign of lazy design. Boundaries must be defined solely through:
- **Tonal Shifts:** Transitioning from `surface` (#101415) to `surface_container_low` (#191C1D).
- **Whitespace:** Using the `16` (5.5rem) token to separate thoughts.
- **Micro-elevation:** A `surface_container` card sitting on a `surface_dim` background.

### Surface Hierarchy & Nesting
Treat the UI as a series of physical layers—like stacked sheets of fine paper.
- **Base Layer:** `surface` (#101415) for the main page body.
- **Nested Content:** Use `surface_container` (#1D2021) for grouped content.
- **Floating Elements:** Use `surface_bright` (#363A3B) only for high-priority interactive elements.

### The "Glass & Gradient" Rule
To ensure the interface feels "custom" rather than "templated," apply a subtle **Radial Glow** to hero sections. Use a gradient from `primary_container` (#80958F) at 15% opacity to `background` (#101415) at 100%. For floating navigation or modals, use Glassmorphism: `surface_variant` at 60% opacity with a `20px` backdrop-blur.

---

## 3. Typography: Editorial Authority
We pair the geometric precision of **Manrope** for headers with the Swiss-inspired clarity of **Inter** for body copy.

*   **Display (Manrope):** Use `display-lg` (3.5rem) with a letter-spacing of `-0.02em`. These should feel like headlines in a high-end fashion magazine—bold, commanding, and sparse.
*   **Body (Inter):** All body text must use a generous line-height (1.6 to 1.8). Use `body-lg` (1rem) for general reading to maintain a premium, accessible feel.
*   **Hierarchy Tip:** Never place a `headline` and `body` text in the same color. Use `on_surface` (#E0E3E4) for headers and `on_surface_variant` (#C1C8C5) for body copy to create an immediate, effortless visual hierarchy.

---

## 4. Elevation & Depth: Tonal Layering
In this design system, we do not "drop shadows"—we "diffuse light."

*   **The Layering Principle:** Depth is achieved by "stacking" tokens. Place a `surface_container_highest` card on a `surface` background. The subtle 3% difference in lightness is all the "border" the eye needs.
*   **Ambient Shadows:** If a floating effect is required (e.g., a dropdown), use a shadow color tinted with `#051F23` (secondary_fixed).
    *   *Spec:* `offset-y: 20px`, `blur: 40px`, `opacity: 8%`.
*   **The "Ghost Border" Fallback:** If accessibility requirements demand a container edge, use the `outline_variant` token at **15% opacity**. It should be felt, not seen.

---

## 5. Components: Minimalist Primitives

### Buttons
*   **Primary:** Solid `primary` (#B5CBC4) with `on_primary` (#21342F) text. Roundedness: `md` (0.375rem). No shadow.
*   **Secondary:** Ghost style. `outline` border at 30% opacity with `primary` text.
*   **States:** On hover, primary buttons should shift to `primary_fixed_dim` and expand by `2px` via a smooth `200ms` cubic-bezier transition.

### Cards & Lists
*   **Rule:** Forbid divider lines.
*   **Implementation:** Use a `surface_container_low` background and `spacing-8` (2.75rem) between list items. For cards, use `rounded-xl` (0.75rem) and rely on the tonal shift from the background to define the shape.

### Input Fields
*   **Style:** Minimalist underline or subtle container. Use `surface_container_high` as the fill. 
*   **Focus State:** The border transitions to `primary` (#B5CBC4) with a subtle outer glow (4px blur) of the same color.

### Signature Component: The "Content Reveal"
Use a large-scale vertical slider or an asymmetric hero image that utilizes the `spacing-24` (8.5rem) token to separate the image from the headline, creating a "breathable" entry point for the user.

---

## 6. Do's and Don'ts

### Do:
*   **Embrace the Void:** Use `spacing-20` between major sections. If it feels like "too much" whitespace, it’s probably just right.
*   **Use Subtle Transitions:** Every hover state should feel like it's "fading in" through a mist. Use longer transition times (300ms–500ms).
*   **Tonal Consistency:** Ensure that `on_surface_variant` is used for all secondary metadata to keep the focus on the primary `on_surface` headlines.

### Don't:
*   **No Pure Black:** Never use `#000000`. Our "black" is the deep teal-tinted `#101415`.
*   **No Harsh Grids:** Avoid boxing everything into equal-width columns. Let text containers be narrower (max-width: 65ch) than the images they accompany.
*   **No Standard Shadows:** Avoid the default "black/gray" shadows found in CSS frameworks. They muddy the sophisticated teal tones of this system.