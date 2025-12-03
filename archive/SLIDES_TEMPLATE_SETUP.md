# Google Slides Template Setup Guide

This guide will help you create and configure the Google Slides template for automatic slide deck generation with **Cashmere style**.

## Cashmere Style Overview

The slide generation system uses a **Cashmere design system** with:
- **Typography**: Modern sans-serif fonts (Montserrat/Lato) with clear hierarchy
- **Colors**: Refined palette (charcoal text, accent highlights, off-white backgrounds)
- **Spacing**: Generous line spacing (115%) and elegant spacing rhythm
- **Voice**: Confident, poetic, grounded tone in all slide content

## Quick Start

1. Create a Google Slides presentation
2. Add slides with placeholder tokens (see below)
3. Share with service account: `sti-slides-generator@my-drive-392615.iam.gserviceaccount.com`
4. Get template ID from URL
5. Run validation script: `python3 validate_slides_template.py <template_id>`
6. Update `config.py` with template ID

## Template Structure

### Slide 1: Hero Slide
Create a cinematic hero slide with:

**Text Placeholders (add as text boxes):**
- `{{TITLE}}` - Main report title (large, prominent)
- `{{SUBTITLE}}` - Executive summary first sentence (medium)
- `{{DATE}}` - Report date (small, bottom corner)

**Optional:**
- `{{LOGO}}` - Add as a shape with this text inside (will be replaced with logo image)

**Design Tips:**
- Use a dramatic background (will be replaced with hero image)
- Large, bold typography
- Generous negative space
- Dark overlay rectangle for text readability (can be styled via API)

### Slide 2: Collage Slide
Create a tile-based collage slide:

**Image Placeholders (add as shapes with text inside each):**
- `{{IMG_1}}` - Shape 1 (will be replaced with first section image)
- `{{IMG_2}}` - Shape 2
- `{{IMG_3}}` - Shape 3
- `{{IMG_4}}` - Shape 4
- `{{IMG_5}}` - Shape 5 (optional)
- `{{IMG_6}}` - Shape 6 (optional)
- `{{IMG_7}}` - Shape 7 (optional)
- `{{IMG_8}}` - Shape 8 (optional)

**Text Placeholder:**
- `{{BIGWORD}}` - Large, angled text (will be rotated ~12°)

**Optional:**
- `{{STICKER}}` - Add as shape (will be replaced with sticker/badge image)

**Design Tips:**
- Grid layout (2x4 or 4x2 recommended)
- Images use CENTER_CROP fill method (fills entire shape)
- Overlay masks can be added in template for rounded corners

### Slides 3+: Content Slides
Create additional slides for report sections:

**For each content slide, add:**
- `{{H1}}` - Section heading (large, bold)
- `{{BULLETS}}` - Bullet points (will be auto-formatted)

**Optional:**
- `{{QUOTE}}` - For highlighted quotes

**Sections that get content slides:**
- Executive Summary
- Signals (key signals list)
- Market Analysis
- Technology Deep-Dive
- Competitive Landscape
- Operator Lens
- Investor Lens
- BD Lens

## Step-by-Step Creation

### 1. Create New Presentation
1. Go to [Google Slides](https://slides.google.com)
2. Create new blank presentation
3. Name it: "STI Report Template"

### 2. Create Hero Slide (Slide 1)
1. Delete default slides, keep one blank slide
2. Add text boxes with:
   - Large text box: Type `{{TITLE}}`
   - Medium text box: Type `{{SUBTITLE}}`
   - Small text box (bottom): Type `{{DATE}}`
3. Style them (the API will replace text but preserve basic styling)
4. (Optional) Add a rectangle shape, type `{{LOGO}}` inside

### 3. Create Collage Slide (Slide 2)
1. Add new slide
2. Create 4-8 rectangles (shapes) in a grid
3. Inside each rectangle, type one of: `{{IMG_1}}`, `{{IMG_2}}`, etc.
4. Add large text box, type: `{{BIGWORD}}`
5. (Optional) Add small shape for `{{STICKER}}`

### 4. Create Content Slides (Slides 3+)
For each section you want:
1. Add new slide
2. Add large heading text box: Type `{{H1}}`
3. Add body text box: Type `{{BULLETS}}`
4. Format with bullets (API will populate content)

### 5. Share Template
1. Click "Share" button in Google Slides
2. Add email: `sti-slides-generator@my-drive-392615.iam.gserviceaccount.com`
3. Set permission: **Viewer** (read-only is sufficient)
4. **Uncheck** "Notify people" (service accounts don't have email)
5. Click "Send"

### 6. Get Template ID
From the Google Slides URL:
```
https://docs.google.com/presentation/d/TEMPLATE_ID_HERE/edit
```
Copy the `TEMPLATE_ID_HERE` part.

### 7. Validate Template
Run the validation script:
```bash
python3 validate_slides_template.py <template_id>
```

This will check:
- ✅ All required placeholders are present
- ✅ Template is accessible to service account
- ✅ Structure is correct

### 8. Update Config
Edit `config.py`:
```python
ENABLE_SLIDES_GENERATION = True
GOOGLE_SLIDES_TEMPLATE_ID = "your-template-id-here"
```

## Fonts & Theme Configuration

### Cashmere Fonts

The system uses **Montserrat** as the primary Cashmere brand font. To ensure proper font rendering:

1. **Add Google Fonts to Template**:
   - In Google Slides, go to **More fonts** (Font dropdown → "More fonts")
   - Search for "Montserrat" and add it
   - Also add "Roboto" and "Arial" as fallbacks

2. **Set Theme Fonts** (Optional):
   - In Google Slides, go to **Theme** → **Theme builder**
   - Set default font for Headings to **Montserrat**
   - Set default font for Body to **Montserrat**
   - This ensures placeholders inherit the correct font

3. **Font Fallback Behavior**:
   - If Montserrat is not available, the system will use Roboto, then Arial
   - The API will log a warning if a font is not recognized
   - Google Slides API defaults unrecognized fonts to Arial

### Theme Colors

The Cashmere style uses a refined color palette:

- **Primary Text**: Charcoal (#333333) - softer than pure black
- **Accent Color**: Dark blue (#34695E) - for highlights and bullets
- **Background**: Light ivory (#FAF7F3) - off-white for all slides
- **Hero Text**: White - for text on dark overlays
- **Subtle Text**: Medium gray - for secondary text

**To set theme colors in template** (optional):
1. In Google Slides, go to **Theme** → **Theme builder**
2. Set theme colors:
   - Primary = Accent color
   - Accent1 = Accent color
   - Background1 = Light ivory
3. The API will use these theme colors when available, with RGB fallbacks

**Note**: All colors are defined in `slides_template_config.py`. If you update colors there, you may want to update the template theme as well for consistency.

## Line Spacing & Typography

### Line Spacing

The Cashmere style uses **115% line height** for readability and elegance:
- Applied automatically to all body text and bullet paragraphs
- Bullet lists use `COLLAPSE_LISTS` spacing mode for tight, cohesive lists
- This creates an airy, professional look without cramped text

### Typography Hierarchy

- **Hero Title**: 56pt, bold
- **Hero Subtitle**: 24pt, normal weight
- **Content Title**: 36pt, bold
- **Body Text**: 18pt, normal weight
- **Meta Text** (dates, captions): 14pt, normal weight
- **Footnotes**: 12pt, normal weight

All sizes are configured in `slides_template_config.py` and can be adjusted there.

## Section Slide Layout (Optional)

If you want section divider slides (e.g., "Market Analysis", "Investor Lens"):

1. Create a new slide layout in the template
2. Name it "Cashmere Section Header" or similar
3. Add a text placeholder with `{{SECTION_TITLE}}`
4. Style with:
   - Full-bleed accent background or image with overlay
   - Centered title in white text (if on dark background)
   - Large, bold typography

**Note**: Section slides are currently optional. The system will create content slides for each section automatically.

## Placeholder Reference

| Placeholder | Required | Slide | Description |
|------------|----------|-------|-------------|
| `{{TITLE}}` | ✅ | 1 (Hero) | Main report title |
| `{{SUBTITLE}}` | ✅ | 1 (Hero) | First sentence of executive summary |
| `{{DATE}}` | ✅ | 1 (Hero) | Report generation date |
| `{{LOGO}}` | ❌ | 1 (Hero) | Logo image (optional) |
| `{{IMG_1}}` | ✅ | 2 (Collage) | First section image |
| `{{IMG_2}}` | ✅ | 2 (Collage) | Second section image |
| `{{IMG_3}}` | ✅ | 2 (Collage) | Third section image |
| `{{IMG_4}}` | ✅ | 2 (Collage) | Fourth section image |
| `{{IMG_5}}` | ✅ | 2 (Collage) | Fifth section image (optional) |
| `{{IMG_6}}` | ✅ | 2 (Collage) | Sixth section image (optional) |
| `{{IMG_7}}` | ✅ | 2 (Collage) | Seventh section image (optional) |
| `{{IMG_8}}` | ✅ | 2 (Collage) | Eighth section image (optional) |
| `{{BIGWORD}}` | ✅ | 2 (Collage) | Large angled word |
| `{{STICKER}}` | ❌ | 2 (Collage) | Sticker/badge image (optional) |
| `{{H1}}` | ✅ | 3+ (Content) | Section heading |
| `{{BULLETS}}` | ✅ | 3+ (Content) | Bullet points |
| `{{QUOTE}}` | ❌ | 3+ (Content) | Highlighted quote (optional) |

## Testing

After setup, test with an existing report:
```bash
# Generate a report (will automatically create slides if enabled)
python3 run_report.py "your query here"
```

Check the report directory for:
- `slides_url.txt` - Link to generated presentation
- `slides_export.pdf` - Exported PDF version
- `metadata.json` - Will include slides info

## Troubleshooting

### Template not found (404)
- Verify template ID is correct
- Check template exists in Google Drive

### Permission denied (403)
- Verify template is shared with service account
- Check service account email: `sti-slides-generator@my-drive-392615.iam.gserviceaccount.com`
- Ensure permission is at least "Viewer"

### Placeholders not replaced
- Run validation script to check all placeholders exist
- Verify placeholder text matches exactly (case-sensitive)
- Check template structure matches expected layout

### Images not appearing
- Images must be generated first (hero and section images)
- Images are uploaded to Drive and may take a moment
- Check report directory has `images/` folder with PNG files
- If an image fails to load, a placeholder rectangle will be created automatically

## Fallback Measures

### Font Fallbacks

The system includes a robust font fallback chain:
1. **Primary**: Montserrat (Cashmere brand font)
2. **Fallback 1**: Roboto (Google Font)
3. **Fallback 2**: Arial (system default)

**If fonts fail**:
- The API will log a warning: "Font X not found, defaulted to Arial"
- To fix: Add the font via "More fonts" in Google Slides UI
- The system prefers Google Fonts to avoid Arial fallback

### Image Fallbacks

**If an image fails to load**:
- A placeholder rectangle will be created automatically
- Placeholder uses the alternate fill color (light gray)
- Placeholder displays "Image not available" text
- The slide structure remains intact

**Common image issues**:
- Image file not found → placeholder created
- Image too large (>50MB or >25MP) → upload may fail, placeholder created
- Invalid image format → placeholder created
- Drive upload failure → placeholder created

**Image validation**:
- Supported formats: PNG, JPEG, GIF
- Max size: 50MB
- Max resolution: 25MP
- URLs must be publicly accessible and <2KB in length

### Content Fallbacks

**If content is missing**:
- Empty sections are skipped
- Missing bullets show empty bullet list
- Missing images show placeholders
- The deck still generates successfully

## Animation Setup

**Important**: Animations cannot be created via the Google Slides API. All animations must be set in the template.

### Setting Animations

1. In Google Slides, select the slide or element
2. Go to **Slide** → **Transition** or **Animate**
3. For content slides with bullets:
   - Apply "Fade in on click" to each bullet level
   - This ensures bullets appear one by one during presentation

**Note**: Animations set in the template will carry over to generated slides when the content structure matches. The API preserves animation settings when replacing text in placeholders.

## Configuration Reference

All Cashmere style settings are in `slides_template_config.py`:

- **Fonts**: `CASHMERE_FONT_FAMILY`, `FONT_FALLBACKS`
- **Colors**: `THEME_COLORS` dictionary
- **Sizes**: `FONT_SIZES` dictionary
- **Spacing**: `LINE_SPACING`, `SPACING` dictionary
- **Layout**: `LAYOUT` dictionary (dimensions in EMU)

To customize the style, edit these values in `slides_template_config.py` and update your template accordingly.

