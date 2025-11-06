<!-- 52654b92-e97d-4232-bf92-b1de3fab1eec ff952ee2-6faa-4f77-8fc9-9f4d69a0d466 -->
# Editorial Quality Fixes for Publication

## Overview

Fix five critical editorial issues identified in the latest report to meet publication standards.

## Root Causes

### 1. Coverage Window Mismatch

**Problem:** Header shows "Oct 21–Oct 28" but signals include Oct 29–Oct 31 dates

**Root Cause:** LLM is generating signal dates based on content interpretation, not strictly constraining them to the source date range

### 2. Vendor-Asserted Numbers  

**Problem:** Claims like "200+ models" and "400+ models" come from sponsor content without qualification

**Root Cause:** No metadata tracking for vendor-asserted vs independently-verified claims

### 3. DYNA-1 Sourcing Alignment  

**Problem:** Specific DYNA-1 deployment claims aren't directly sourced

**Root Cause:** LLM synthesizing details beyond what sources explicitly state

### 4. Tangential Sources  

**Problem:** OpenAI/SAI acquisition (source [5]) not used in analysis

**Root Cause:** No filtering of sources that don't contribute to the main thesis

### 5. Title & Copy Polish  

**Problem:** Inconsistent capitalization, hyphenation, and paragraph length

**Root Cause:** No house style enforcement in generation

---

## Solutions

### Fix 1: Coverage Window Alignment

**Approach:** Strict signal date validation in HTML converter

**File:** `html_converter_agent.py` - Add to `_parse_signals()`

```python
def _parse_signals(self, signals_text: str, date_range: str) -> List[Dict[str, Any]]:
    """Parse signals and validate dates are within coverage window"""
    signals = []
    
    # Extract date range from metadata
    date_match = re.search(r'(\w+ \d+)–(\w+ \d+), (\d{4})', date_range)
    if date_match:
        end_date_str = f"{date_match.group(2)}, {date_match.group(3)}"
        try:
            end_date = datetime.strptime(end_date_str, '%b %d, %Y')
        except:
            end_date = datetime.now()
    else:
        end_date = datetime.now()
    
    # Parse each signal and validate/adjust dates
    for line in signals_text.strip().split('\n\n'):
        if not line.strip():
            continue
            
        # Extract date from signal
        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', line)
        if date_match:
            signal_date_str = date_match.group(1)
            try:
                signal_date = datetime.strptime(signal_date_str, '%Y-%m-%d')
                
                # If signal date is after end_date, mark as forecast
                if signal_date > end_date:
                    # Tag as forecast and move to watchlist section
                    logger.warning(f"Signal date {signal_date_str} is after coverage window, marking as forecast")
                    # Could either skip or tag - for now, skip
                    continue
                    
            except:
                pass
        
        # Parse signal content
        # ... existing signal parsing logic ...
```

**Alternative:** Update prompt to strictly enforce date constraints

### Fix 2: Vendor-Asserted Qualification

**File:** `enhanced_mcp_agent.py` or analysis server

**Add metadata tracking:**

```python
# In _extract_signals or analysis functions
def _classify_claim_source(self, source_url: str, source_publisher: str) -> str:
    """Classify if claim is vendor-asserted or independently verified"""
    vendor_indicators = [
        '/sponsor/',
        'press-release',
        'company-blog',
        source_publisher.lower() in ['openai', 'anthropic', 'nexos', 'openrouter']
    ]
    
    if any(indicator in source_url.lower() or indicator for indicator in vendor_indicators):
        return "vendor-asserted"
    return "independent"

# In signal generation, add qualifier
if claim_source == "vendor-asserted":
    measurable += " (vendor-asserted via sponsor content)"
```

**Simpler approach:** Add post-processing in HTML converter to detect and tag vendor claims

### Fix 3: DYNA-1 Sourcing Qualification

**File:** `servers/analysis_server.py` or signal extraction

**Add qualification template:**

```python
# When generating claims without direct source support
if not directly_cited:
    prefix_qualifier = "Reports indicate"
    # or "According to industry sources"
    # or "Multiple sources suggest"
```

**Better:** Update prompt to require explicit source citations for specific claims

### Fix 4: Remove Tangential Sources

**File:** `html_converter_agent.py` - Add source relevance check

```python
def _filter_relevant_sources(self, sources: List[Dict], signals_html: str, analysis_sections: List[str]) -> List[Dict]:
    """Remove sources not cited in signals or analysis"""
    cited_source_ids = set()
    
    # Extract all citation references from signals
    citation_pattern = r'\[(\d+)\]'
    all_content = signals_html + ' '.join(analysis_sections)
    cited_source_ids.update(int(m.group(1)) for m in re.finditer(citation_pattern, all_content))
    
    # Filter to only cited sources
    return [s for s in sources if s['id'] in cited_source_ids]
```

### Fix 5: Title & Copy Polish

**File:** `html_converter_agent.py` - Add formatting methods

```python
def _apply_house_style_title(self, title: str) -> str:
    """Apply house style: Title Case with hyphens"""
    # Capitalize major words, preserve hyphens
    words = title.split()
    capitalized = []
    for word in words:
        if '—' in word or word.lower() in ['and', 'or', 'the', 'a', 'an', 'of', 'for']:
            capitalized.append(word.lower() if word.lower() in ['and', 'or', 'the', 'a', 'an', 'of', 'for'] else word)
        else:
            capitalized.append(word.capitalize())
    
    result = ' '.join(capitalized)
    
    # Fix specific patterns
    result = result.replace('Llm', 'LLM')
    result = result.replace('Ai', 'AI')
    result = result.replace('And', 'and')
    
    return result

def _split_long_paragraphs(self, text: str, max_words: int = 150) -> str:
    """Split overly long paragraphs for readability"""
    # Already implemented in _segment_into_paragraphs
    return self._segment_into_paragraphs(text, max_words)
```

---

## Implementation Priority

### Priority 1: Quick Fixes (No Breaking Changes)

1. ✅ Title case and hyphenation fix in HTML converter
2. ✅ Remove uncited sources in HTML rendering
3. ✅ Add vendor-asserted tags in HTML output

### Priority 2: Validation Layer (Prevents Future Issues)

4. ⚠️ Signal date validation against coverage window
5. ⚠️ Source citation requirement for specific claims

### Priority 3: Generation Quality (Requires Prompt Engineering)

6. 📝 Update prompts to enforce date constraints
7. 📝 Update prompts to qualify vendor-asserted claims
8. 📝 Update prompts to require explicit sourcing

---

## Specific Fixes for Current Report

### Fix A: Title

**Current:** `Tech Brief — Llm Driven Robotics And Embodied Ai`

**Fixed:** `Tech Brief — LLM-Driven Robotics and Embodied AI`

### Fix B: Date Range — **OPTION B: Forecast Badge**

**Current:** Oct 21–Oct 28 (with Oct 29–31 signals)

**Decision:** Keep metadata bar as `Oct 21–Oct 28, 2025` and add **Forecast** badge to post-Oct 28 signals

**Rationale:** Maintains editorial integrity with the "Generated: Oct 28" timestamp while preserving future-dated signals as forecasts

**Implementation:**

1. Add CSS for forecast badge:
   ```css
   .badge-forecast { 
       background: #e2e3e5; 
       color: #343a40; 
       border: 1px solid #d6d8db; 
   }
   ```

2. Identify signals dated > Oct 28, 2025 and append forecast badge:
   ```html
   <span class="badge badge-forecast">Forecast</span>
   ```

3. Affected signals (from report):

   - Oct 29: OpenRouter 400+ LLMs signal
   - Oct 30: DYNA-1 deployment signal  
   - Oct 31: Elloe AI verification layer signals (×2)

### Fix C: Vendor Claims

**Current:** "Nexos.ai's unified API to 200+ LLMs"

**Fixed:** "Nexos.ai's unified API to 200+ LLMs (vendor-asserted via sponsor content)"

### Fix D: DYNA-1 Sourcing

**Current:** "Dyna Robotics' commercially deployed DYNA-1 performing..."

**Fixed:** "Reports indicate Dyna Robotics' DYNA-1 deployments include..."

### Fix E: Remove Source [5]

OpenAI/SAI acquisition not cited in analysis - remove from sources list

---

## Testing

1. Generate new report and verify:

   - Title matches house style
   - All signal dates ≤ end date
   - Vendor claims have qualifiers
   - All sources are cited
   - Paragraphs < 150 words

2. Run validation:
   ```python
   assert all(signal_date <= end_date for signal in signals)
   assert all(source_id in cited_ids for source_id in source_ids)
   ```


---

## Rollout

1. **Immediate:** Apply title and source filtering fixes
2. **Next:** Add vendor-asserted qualification
3. **Future:** Update prompts for generation-level quality

### To-dos

- [ ] Create html_converter_agent.py with HTMLConverterAgent class and markdown parsing logic
- [ ] Create templates/report_template.html with inline CSS implementing Bloomberg/FT style
- [ ] Modify file_utils.py to integrate HTML generation into save_enhanced_report()
- [ ] Add --html CLI flag to run_report.py for optional HTML generation
- [ ] Add markdown parsing library to requirements.txt
- [ ] Test HTML conversion on existing report and verify rendering/printing