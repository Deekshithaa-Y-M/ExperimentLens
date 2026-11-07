# 🧪 A/B Test Statistical Significance Calculator

A robust, web-based utility designed to calculate the statistical significance of A/B tests. Product managers, marketers, and data analysts can seamlessly input visitor and conversion data for Control and Variant groups to quickly determine conversion rates, uplift, p-values, and confidence intervals.


## 💡 About
This is a lightweight, static frontend application (HTML, CSS, JavaScript) that performs standard A/B test calculations. It serves as a reliable tool for quick, offline checks and as an educational resource for interpreting split-test results without relying on heavy third-party platforms.

## ✨ Features
- **Instant Calculations:** Rapidly compute conversion rates, absolute uplift, and relative uplift.
- **Statistical Rigor:** Outputs accurate Z-scores, p-values, and confidence intervals for conversion rates.
- **Actionable Output:** Clear, plain-language guidance on statistical significance thresholds.
- **Robust Testing:** Backed by a rigorous testing suite (unit tests and property‑based tests via Jest + fast-check) to validate calculation correctness across extreme edge cases.
- **Zero Dependencies:** A clean, responsive UI built with vanilla HTML/CSS/JS. Its small production footprint means it is completely portable and easy to host.

## 🧮 The Math
This tool calculates significance using a **two‑proportion Z‑test** (normal approximation). The Z-score is calculated as:

**Z = (p₁ - p₂) / √[ p(1 - p) * (1/n₁ + 1/n₂) ]**

Where:
- **`p₁`, `p₂`** = Sample proportions (conversion rates) for the Control and Variant groups.
- **`n₁`, `n₂`** = Sample sizes (total visitors).
- **`p`** = The pooled proportion, calculated as `(x₁ + x₂) / (n₁ + n₂)`, where `x₁` and `x₂` are the total conversions.

> **Note on Methodology:** > The p‑value is derived from the Z-score and is **two‑tailed** by default. Confidence intervals utilize the normal approximation method. For smaller sample sizes or extremely low conversion counts, consider using Wilson score intervals or exact methods.

## 🚀 Usage

1. **Launch:** Open the [live demo](https://deekshithaa-y-m.github.io/ExperimentLens/) or open `index.html` locally in any web browser.
2. **Input Data:** Enter your experiment values for both the Control (A) and Variant (B) groups:
   - *Visitors* (Total sample size)
   - *Conversions* (Successful actions)
3. **Analyze Results:** The calculator will immediately display:
   - Conversion rates for each group
   - Absolute and relative uplift
   - Z-score and p‑value
   - Confidence intervals
4. **Interpret:** Use the calculated p‑value alongside your practical business context to make a decision. 

**Example Interpretation:**
* **`p < 0.05`**: Commonly considered statistically significant at the 5% alpha level. 
* *Tip:* Always check the magnitude of the uplift. A difference can be statistically significant but practically insignificant if the relative uplift is negligible.

## 💻 Local Setup & Installation
Because this is a static web app, no complex build pipelines are required. You can run it directly from your file system or serve it using a lightweight static server.

1. Clone the repository:
   ```bash
   git clone [https://github.com/Deekshithaa-Y-M/ab-test-calculator.git](https://github.com/Deekshithaa-Y-M/ab-test-calculator.git)
