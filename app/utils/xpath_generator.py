"""
XPath Generator Utility

This module analyzes HTML structure to automatically generate XPath patterns
that can extract field values based on their labels.
"""

from lxml import html, etree
from typing import Dict, List, Optional, Tuple, Any
import re


def normalize_text(text: str) -> str:
    """Normalize text for comparison (remove extra whitespace, lowercase)"""
    if not text:
        return ""
    return ' '.join(text.strip().split()).lower()


# Labels that we intentionally IGNORE for XPath generation/validation.
# For example, "Client" in some EMRs is not needed for automation and is
# difficult to map reliably, so we skip it entirely and never treat it as
# a failure for the overall XPath generation.
IGNORED_LABELS = {
    "client",               # matches "Client" / "Client:" after normalization + rstrip(':')
    "location of session",  # matches "Location of Session:" etc.
}


def is_popup_visible(popup: html.HtmlElement) -> bool:
    """
    Check if a popup is currently visible/open.
    Checks for common visibility indicators.
    
    Args:
        popup: Popup element to check
    
    Returns:
        True if popup appears to be visible, False otherwise
    """
    # Check class for visibility indicators
    popup_class = (popup.get('class') or '').lower()
    visible_classes = ['show', 'in', 'visible', 'active', 'open', 'display']
    has_visible_class = any(vc in popup_class for vc in visible_classes)
    
    # Check style attribute
    popup_style = (popup.get('style') or '').lower()
    has_display_block = 'display:block' in popup_style or 'display: flex' in popup_style
    has_display_none = 'display:none' in popup_style
    
    # Check aria-hidden
    aria_hidden = popup.get('aria-hidden', '').lower()
    is_aria_visible = aria_hidden == 'false' or aria_hidden == ''
    
    # Popup is visible if:
    # - Has visible class AND not display:none, OR
    # - Has display:block/flex in style, OR
    # - aria-hidden is false/empty (and no display:none)
    is_visible = (
        (has_visible_class and not has_display_none) or
        (has_display_block and not has_display_none) or
        (is_aria_visible and not has_display_none)
    )
    
    return is_visible


def detect_popup_container(tree: html.HtmlElement, field_labels: Optional[List[str]] = None) -> Optional[html.HtmlElement]:
    """
    Dynamically detect popup/modal container in HTML using multiple heuristics.
    Works for any popup structure, not just hardcoded patterns.
    Prioritizes currently visible/open popups.
    
    Args:
        tree: Parsed HTML tree
        field_labels: Optional list of field labels to help identify popup container
    
    Returns:
        Popup container element if found, None otherwise
    """
    print(f"\n🔍 Starting dynamic popup detection...")
    
    # Strategy 1: If we have field labels, find popup that contains them (SMARTEST)
    if field_labels and len(field_labels) > 0:
        print(f"   Strategy 1: Finding popup that contains the field labels...")
        try:
            # Find all potential popups first
            all_popups = []
            role_patterns = [
                "//*[@role='dialog']",
                "//*[@role='alertdialog']",
            ]
            for pattern in role_patterns:
                try:
                    matches = tree.xpath(pattern)
                    all_popups.extend(matches)
                except:
                    continue
            
            # Also check for modal/popup class patterns (but only top-level containers, not nested)
            class_patterns = [
                "//div[contains(translate(@class, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'modal')]",
                "//div[contains(translate(@class, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'popup')]",
            ]
            for pattern in class_patterns:
                try:
                    matches = tree.xpath(pattern)
                    # Filter to only top-level popup containers (not nested inside other popups)
                    for match in matches:
                        # Check if this element is not a descendant of another popup we already have
                        is_nested = False
                        for existing_popup in all_popups:
                            if match in existing_popup.xpath(".//*"):
                                is_nested = True
                                break
                        if not is_nested:
                            all_popups.append(match)
                except:
                    continue
            
            # Remove duplicates by element identity
            unique_popups = []
            seen_ids = set()
            for popup in all_popups:
                popup_id = id(popup)
                if popup_id not in seen_ids:
                    seen_ids.add(popup_id)
                    unique_popups.append(popup)
            
            all_popups = unique_popups
            print(f"      Found {len(all_popups)} unique popup container(s)")
            
            # For each popup, check if it contains the field labels
            # Prioritize visible popups
            best_popup = None
            best_score = 0
            visible_popups = []
            hidden_popups = []
            
            # Separate visible and hidden popups
            for popup in all_popups:
                if is_popup_visible(popup):
                    visible_popups.append(popup)
                else:
                    hidden_popups.append(popup)
            
            print(f"      Found {len(visible_popups)} visible popup(s) and {len(hidden_popups)} hidden popup(s)")
            
            # Check visible popups first (they're more likely to be the current one)
            popups_to_check = visible_popups + hidden_popups
            
            for popup in popups_to_check:
                labels_found = 0
                popup_id = popup.get('id', 'N/A')
                popup_class = popup.get('class', 'N/A')
                is_visible = is_popup_visible(popup)
                visibility_marker = "👁️ VISIBLE" if is_visible else "👻 HIDDEN"
                
                for label in field_labels[:5]:  # Check first 5 labels
                    # Search for label text INSIDE this popup only (strict - must be descendant)
                    label_clean = label.lower().strip().rstrip(':').rstrip()  # Remove trailing colon and spaces
                    
                    # Search directly in popup elements, but exclude nested popups
                    # Get all elements in popup, but filter out any that are inside nested popups
                    all_popup_elements = popup.xpath(".//*")
                    popup_elements = []
                    
                    for elem in all_popup_elements:
                        # Check if this element is inside a nested popup (skip it if so)
                        is_in_nested_popup = False
                        current = elem.getparent()
                        while current is not None and current != popup:
                            # Check if current element is a popup (has role=dialog or modal class)
                            if (current.get('role') in ['dialog', 'alertdialog'] or
                                'modal' in (current.get('class') or '').lower()):
                                is_in_nested_popup = True
                                break
                            current = current.getparent()
                        
                        if not is_in_nested_popup:
                            popup_elements.append(elem)
                    
                    label_found = False
                    for elem in popup_elements:
                        # Get direct text of this element (not from nested children)
                        direct_text = (elem.text or '').strip().lower()
                        # Also check if label appears as a label/span/div text (common patterns)
                        elem_tag = elem.tag.lower()
                        
                        # Check direct text first
                        if direct_text:
                            if (label_clean == direct_text or
                                (label_clean in direct_text and len(label_clean) > 5)):
                                label_found = True
                                break
                        
                        # Check element's own text content (but be more strict)
                        elem_text = elem.text_content().strip().lower()
                        if not elem_text or elem_text == direct_text:
                            continue
                        
                        # More strict matching - label should be significant part of element
                        # Only match if label is at the start of the text or is the main content
                        if (label_clean == elem_text or
                            (elem_text.startswith(label_clean) and len(label_clean) > 5) or
                            (len(label_clean.split()) >= 2 and 
                             all(word in elem_text for word in label_clean.split() if len(word) > 3) and
                             elem_text.count(' ') < 10)):  # Limit to elements with reasonable text length
                            label_found = True
                            break
                    
                    if label_found:
                        labels_found += 1
                
                print(f"      Popup <{popup.tag}> id='{popup_id}' {visibility_marker}: contains {labels_found} labels")
                
                # Track the popup with most labels
                # Give bonus points to visible popups (they're more likely to be the current one)
                score = labels_found
                if is_visible:
                    score += 0.5  # Bonus for visible popups
                
                if score > best_score:
                    best_score = score
                    best_popup = popup
                    print(f"         → New best popup! Score: {labels_found} labels (+ visibility bonus: {score})")
            
            # If we found a popup with at least 2 labels, check for nested modals inside it
            if best_popup and best_score >= 2:
                print(f"   ✅ Selected popup containing {best_score} field labels: <{best_popup.tag}> id='{best_popup.get('id', 'N/A')}' class='{best_popup.get('class', 'N/A')}'")
                
                # Check if there are nested modals/dialogs inside this popup that might contain MORE labels
                nested_modals = best_popup.xpath(".//*[@role='dialog' or @role='alertdialog']")
                if nested_modals:
                    print(f"   🔍 Found {len(nested_modals)} nested modal(s) inside - checking if they contain more labels...")
                    best_nested = None
                    best_nested_score = best_score
                    
                    for nested in nested_modals:
                        nested_labels = 0
                        nested_id = nested.get('id', 'N/A')
                        for label in field_labels[:5]:
                            label_clean = label.lower().strip().rstrip(':').rstrip()
                            nested_elements = nested.xpath(".//*")
                            for elem in nested_elements:
                                elem_text = elem.text_content().strip().lower()
                                if (label_clean in elem_text or 
                                    label_clean.replace(':', '') in elem_text.replace(':', '') or
                                    any(word in elem_text for word in label_clean.split() if len(word) > 3)):
                                    nested_labels += 1
                                    break
                        
                        print(f"      Nested modal id='{nested_id}': contains {nested_labels} labels")
                        if nested_labels > best_nested_score:
                            best_nested_score = nested_labels
                            best_nested = nested
                    
                    if best_nested and best_nested_score > best_score:
                        print(f"   ✅ Found nested modal with {best_nested_score} labels (better than parent with {best_score}) - using nested modal")
                        return best_nested
                    elif best_nested and best_nested_score == best_score:
                        print(f"   ℹ️  Nested modal has same score ({best_nested_score}) - using parent popup")
                
                return best_popup
            elif best_popup and best_score > 0:
                print(f"   ⚠️  Best popup only contains {best_score} label(s), but using it anyway")
                return best_popup
            
            print(f"   ⚠️  No popup found containing the field labels")
        except Exception as e:
            print(f"   Strategy 1 error: {e}")
    
    # Strategy 2: Look for elements with role attributes (fallback)
    print(f"   Strategy 2: Checking role attributes...")
    role_patterns = [
        "//*[@role='dialog']",
        "//*[@role='alertdialog']",
    ]
    for pattern in role_patterns:
        try:
            matches = tree.xpath(pattern)
            if matches:
                popup = matches[0]
                print(f"   ✅ Found by role: <{popup.tag}> role='{popup.get('role')}'")
                return popup
        except:
            continue
    
    # Strategy 3: Look for common popup indicators in class/id (case-insensitive)
    print(f"   Strategy 3: Checking class/id patterns...")
    indicator_patterns = [
        "//*[contains(translate(@class, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'modal')]",
        "//*[contains(translate(@class, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'popup')]",
        "//*[contains(translate(@class, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'dialog')]",
        "//*[contains(translate(@class, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'overlay')]",
        "//*[contains(translate(@id, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'modal')]",
        "//*[contains(translate(@id, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'popup')]",
        "//*[contains(translate(@id, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'dialog')]",
    ]
    for pattern in indicator_patterns:
        try:
            matches = tree.xpath(pattern)
            if matches:
                popup = matches[0]
                print(f"   ✅ Found by class/id pattern: <{popup.tag}>")
                return popup
        except:
            continue
    
    # Strategy 4: If we have field labels, find common ancestor container
    if field_labels and len(field_labels) > 0:
        print(f"   Strategy 3: Analyzing field locations to find common container...")
        try:
            # Find elements containing the field labels
            label_elements = []
            for label in field_labels[:3]:  # Check first 3 labels
                elem = find_element_with_text(tree, label, exact=False)
                if elem:
                    label_elements.append(elem)
            
            if len(label_elements) >= 2:
                # Find common ancestor of label elements
                # Get ancestors of first label
                ancestors1 = []
                current = label_elements[0]
                while current is not None:
                    ancestors1.append(current)
                    current = current.getparent()
                
                # Check if other labels share a common ancestor
                for ancestor in ancestors1:
                    if ancestor.tag in ['body', 'html']:
                        continue
                    
                    # Check if at least 2 labels are descendants of this ancestor
                    descendant_count = 0
                    for label_elem in label_elements:
                        if label_elem in ancestor.xpath('.//*') or label_elem == ancestor:
                            descendant_count += 1
                    
                    if descendant_count >= 2:
                        # This might be a popup container
                        # Check if it's likely a popup (has form-like structure, not main page)
                        ancestor_text = ancestor.text_content()[:200] if ancestor.text_content() else ""
                        if len(ancestor_text) < 5000:  # Popups are usually smaller
                            print(f"   ✅ Found common container by field analysis: <{ancestor.tag}>")
                            print(f"      Contains {descendant_count} field labels")
                            return ancestor
        except Exception as e:
            print(f"   Strategy 3 error: {e}")
    
    # Strategy 5: Look for elements with popup-like styling indicators
    print(f"   Strategy 5: Checking for popup-like structure...")
    try:
        # Look for divs that might be popups (have z-index, fixed/absolute positioning hints)
        # This is a fallback - look for containers that are likely popups
        all_divs = tree.xpath("//div")
        for div in all_divs:
            div_class = div.get('class', '').lower()
            div_id = div.get('id', '').lower()
            div_style = div.get('style', '').lower()
            
            # Check for popup indicators
            has_z_index = 'z-index' in div_style
            has_fixed = 'position:fixed' in div_style or 'position: absolute' in div_style
            has_backdrop = 'backdrop' in div_class or 'backdrop' in div_id
            has_modal_like = any(word in div_class or word in div_id 
                               for word in ['modal', 'popup', 'dialog', 'overlay', 'window', 'panel'])
            
            # If it has multiple popup indicators, it's likely a popup
            indicators = sum([has_z_index, has_fixed, has_backdrop, has_modal_like])
            if indicators >= 2:
                print(f"   ✅ Found by structure analysis: <{div.tag}> (indicators: {indicators})")
                return div
    except Exception as e:
        print(f"   Strategy 4 error: {e}")
    
    print(f"   ❌ No popup detected with dynamic strategies")
    return None


def generate_popup_css_selector(popup_container: html.HtmlElement) -> str:
    """
    Generate a CSS selector for the popup container.
    Prioritizes stable attributes (id, class, role) for reliable selection.
    
    Args:
        popup_container: The popup container element
    
    Returns:
        CSS selector string for the popup container
    """
    popup_tag = popup_container.tag
    popup_attrs = dict(popup_container.attrib)
    
    # Priority: id > class > role > tag only
    if 'id' in popup_attrs and popup_attrs['id']:
        # Use id with starts-with pattern if it has dynamic suffix (e.g., id^="view_sessions_notes_md")
        popup_id = popup_attrs['id']
        # Check if ID looks dynamic (has numbers or common patterns)
        if any(char.isdigit() for char in popup_id) or '_' in popup_id:
            # Try to find a stable prefix
            parts = popup_id.split('_')
            if len(parts) > 1:
                # Use prefix pattern: div[id^="view_sessions_notes"]
                prefix = '_'.join(parts[:-1])  # Remove last part (likely dynamic)
                return f"{popup_tag}[id^=\"{prefix}\"]"
        return f"{popup_tag}#{popup_id}"
    
    elif 'class' in popup_attrs and popup_attrs['class']:
        # Use class selector - take first class or all if multiple
        classes = popup_attrs['class'].strip().split()
        if classes:
            # Use first class (most stable)
            first_class = classes[0]
            return f"{popup_tag}.{first_class}"
        return popup_tag
    
    elif 'role' in popup_attrs and popup_attrs['role']:
        return f"{popup_tag}[role=\"{popup_attrs['role']}\"]"
    
    else:
        # Fallback to tag only (least specific)
        return popup_tag


def find_element_with_text(tree: html.HtmlElement, text: str, exact: bool = True, 
                           scope: Optional[html.HtmlElement] = None) -> Optional[html.HtmlElement]:
    """
    Find the DEEPEST (most specific) element containing text (case-insensitive).
    Prefers elements with less nested content.
    
    Args:
        tree: Parsed HTML tree
        text: Text to search for
        exact: If True, match exact text; if False, match contains
        scope: Optional element to scope search to (e.g., popup container)
    
    Returns:
        Most specific matching element or None
    """
    text_lower = text.lower().strip()
    search_mode = "exact" if exact else "contains"
    scope_info = f"inside popup" if scope else "entire document"
    
    print(f"      🔍 Searching for label '{text}' ({search_mode} match, {scope_info})...")
    
    # If scope is provided, search only within that scope, otherwise search entire tree
    if scope is not None:
        all_elements = scope.xpath(".//*")
        print(f"      📦 Searching in scope: <{scope.tag}> (found {len(all_elements)} elements)")
    else:
        all_elements = tree.xpath("//*")
        print(f"      📄 Searching entire document (found {len(all_elements)} elements)")
    
    matches = []
    sample_texts = []  # For debugging
    
    for elem in all_elements:
        elem_text = elem.text_content().strip()
        if not elem_text:
            continue
            
        elem_text_lower = elem_text.lower()
        text_clean = text_lower.rstrip(':').rstrip()  # Remove trailing colon
        elem_text_clean = elem_text_lower.rstrip(':').rstrip()
        
        # Collect sample texts for debugging (first 5 non-matching)
        if len(sample_texts) < 5 and text_clean not in elem_text_clean:
            sample_texts.append(elem_text[:50])
        
        # Try exact match first
        if exact:
            if elem_text_lower == text_lower or elem_text_clean == text_clean:
             matches.append(elem)
        else:
            # Contains match - try multiple variations
            # But be more strict: label text should be a significant part of element text
            if (text_clean in elem_text_clean or
                (len(text_clean) > 5 and text_clean.replace(':', '') in elem_text_clean.replace(':', '')) or
                (len(text_clean.split()) >= 2 and all(word in elem_text_clean for word in text_clean.split() if len(word) > 3))):
                matches.append(elem)
    
    if not matches:
        print(f"      ❌ No matches found for '{text}'")
        if sample_texts:
            print(f"      📝 Sample texts found in scope (first 5): {sample_texts}")
        return None
    
    print(f"      ✅ Found {len(matches)} match(es) for '{text}'")
    
    # Find the DEEPEST element (most specific)
    # Priority: 1) Leaf nodes (no children), 2) Smallest text content
    # This prefers <span>Text</span> over <label><span>Text</span></label>
    
    # First try to find leaf nodes (elements with no child elements)
    leaf_matches = [e for e in matches if len(e) == 0]
    
    if leaf_matches:
        # Among leaf nodes, pick the one with smallest text
        deepest = min(leaf_matches, key=lambda e: len(e.text_content()))
        print(f"      ✓ Selected leaf node: <{deepest.tag}> with text: '{deepest.text_content()[:50]}'")
    else:
        # No leaf nodes, pick element with smallest text content
        deepest = min(matches, key=lambda e: len(e.text_content()))
        print(f"      ✓ Selected element: <{deepest.tag}> with text: '{deepest.text_content()[:50]}'")
    
    return deepest


def find_value_element_near_label(tree: html.HtmlElement, label_elem: html.HtmlElement, 
                                   expected_value: str, scope: Optional[html.HtmlElement] = None) -> Optional[html.HtmlElement]:
    """
    Find the MOST SPECIFIC element containing the value near a label element (case-insensitive).
    Prefers deepest/smallest elements with stable attributes.
    
    Args:
        tree: Parsed HTML tree
        label_elem: The label element
        expected_value: The expected value text to find
        scope: Optional element to scope search to (e.g., popup container)
    
    Returns:
        Most specific element containing the value or None
    """
    expected_value_lower = expected_value.strip().lower()
    
    debug_prefix = f"[VALUE NEAR LABEL] '{expected_value[:40]}...'"

    # Get ALL elements (not just those with direct text)
    # If scope is provided, search only within that scope, otherwise search entire tree
    if scope is not None:
        all_elements = scope.xpath(".//*")
        print(f"{debug_prefix} - searching for value inside scoped container <{scope.tag}>")
    else:
        all_elements = tree.xpath("//*")
        print(f"{debug_prefix} - searching for value in entire document")
    
    # Collect all near matches and global candidates, don't return first one.
    # We distinguish between NEAR+EXACT and NEAR+CONTAINS so that we can
    # prefer pure value nodes when strict validation is enabled.
    near_matches = []         # contains (near) or exact (near)
    near_exact_matches = []   # exact (near) only
    all_candidates = []       # global contains/exact, regardless of distance
    
    for val_elem in all_elements:
        elem_text = val_elem.text_content().strip()
        
        if not elem_text:  # Skip empty elements
            continue
            
        elem_text_lower = elem_text.lower()
        
        # Check for exact match or contains match (case-insensitive)
        if elem_text_lower == expected_value_lower or expected_value_lower in elem_text_lower:
            # Track as a general candidate
            all_candidates.append(val_elem)
            # Check if it's reasonably close to the label
            if is_element_near(label_elem, val_elem):
                near_matches.append(val_elem)
                if elem_text_lower == expected_value_lower:
                    near_exact_matches.append(val_elem)
            else:
                # Helpful debug to understand why a good-looking candidate was rejected
                snippet = elem_text[:80].replace("\n", " ")
                print(f"{debug_prefix} - FOUND text match but NOT near label, skipping: '{snippet}'")
    
    if not near_matches:
        # As a fallback, try a structural heuristic:
        # many EMR forms use a pattern where the value is in the NEXT sibling
        # element (often a div.col-md-8) after the label within the same row.
        try:
            parent = label_elem.getparent()
            if parent is not None:
                siblings = list(parent)
                if label_elem in siblings:
                    idx = siblings.index(label_elem)
                    for sib in siblings[idx + 1:]:
                        # Prefer element siblings (skip text nodes etc.)
                        if not isinstance(sib, html.HtmlElement):
                            continue
                        sib_text = sib.text_content().strip()
                        if not sib_text:
                            continue
                        sib_text_lower = sib_text.lower()
                        # Require the expected value to appear in this sibling
                        if expected_value_lower in sib_text_lower:
                            print(f"{debug_prefix} - using STRUCTURAL fallback (following sibling) with text: '{sib_text[:80]}'")
                            return sib
        except Exception as e:
            print(f"{debug_prefix} - structural fallback error: {e}")

        # Final fallback: if we still have no near match but DO have global
        # candidates that contain the expected value, pick the "best" one.
        # This is especially important for grid/row fields (Date, Time In, etc.)
        # where the label might live in a header (<th>) and the value in a body
        # cell (<td>) that is structurally far away in the DOM.
        if all_candidates:
            print(f"{debug_prefix} - using GLOBAL fallback (no near matches, but {len(all_candidates)} candidates found)")
            # Prefer elements with stable attributes first
            stable = [
                e for e in all_candidates
                if 'data-testid' in e.attrib
                or 'data-test-id' in e.attrib
                or (e.get('class') and any(cls in e.get('class') for cls in ['session_date', 'timein', 'timeout']))
            ]
            target_pool = stable or all_candidates
            # Among target pool, prefer leaf nodes with shortest text (closest to pure value)
            leaf_candidates = [e for e in target_pool if len(e) == 0]
            if leaf_candidates:
                return min(leaf_candidates, key=lambda e: len(e.text_content()))
            return min(target_pool, key=lambda e: len(e.text_content()))

        return None
    
    # Find the MOST SPECIFIC element among near matches
    # Priority:
    # 1. Elements with data-testid or data-test-id (most stable)
    # 2. Leaf nodes (no children)
    # 3. Smallest text content
    
    # First, prefer elements with stable test attributes
    # Prefer exact matches if we found any near the label
    target_near = near_exact_matches or near_matches

    stable_matches = [e for e in target_near if 'data-testid' in e.attrib or 'data-test-id' in e.attrib]
    if stable_matches:
        # Among stable elements, prefer leaf nodes
        stable_leaf = [e for e in stable_matches if len(e) == 0]
        if stable_leaf:
            return min(stable_leaf, key=lambda e: len(e.text_content()))
        return min(stable_matches, key=lambda e: len(e.text_content()))
    
    # No stable attributes, prefer leaf nodes
    leaf_matches = [e for e in target_near if len(e) == 0]
    if leaf_matches:
        return min(leaf_matches, key=lambda e: len(e.text_content()))
    
    # Fall back to smallest text content
    return min(target_near, key=lambda e: len(e.text_content()))


def is_element_near(elem1: html.HtmlElement, elem2: html.HtmlElement, max_depth: int = 10) -> bool:
    """
    Check if two elements are near each other in the DOM tree.
    
    Args:
        elem1: First element
        elem2: Second element
        max_depth: Maximum depth to search
    
    Returns:
        True if elements share a common ancestor within max_depth levels
    """
    # Get ancestors for both elements
    ancestors1 = set()
    current = elem1
    depth = 0
    while current is not None and depth < max_depth:
        ancestors1.add(current)
        current = current.getparent()
        depth += 1
    
    # Check if elem2 shares any ancestor
    current = elem2
    depth = 0
    while current is not None and depth < max_depth:
        if current in ancestors1:
            return True
        current = current.getparent()
        depth += 1
    
    return False


def analyze_element_relationship(tree: html.HtmlElement, label_elem: html.HtmlElement, 
                                 value_elem: html.HtmlElement) -> Optional[str]:
    """
    Analyze the structural relationship between label and value elements.
    
    Args:
        tree: Parsed HTML tree
        label_elem: The label element
        value_elem: The value element
    
    Returns:
        XPath pattern fragment describing the relationship, or None
    """
    # Get element details
    label_tag = label_elem.tag
    value_tag = value_elem.tag
    
    label_attrs = dict(label_elem.attrib)
    value_attrs = dict(value_elem.attrib)
    
    # Pattern 1: Direct siblings
    if label_elem.getparent() == value_elem.getparent():
        # Same parent - check if they're siblings
        parent = label_elem.getparent()
        children = list(parent)
        
        try:
            label_idx = children.index(label_elem)
            value_idx = children.index(value_elem)
            
            if value_idx > label_idx:
                # Value comes after label - use following-sibling
                if 'class' in value_attrs:
                    return f"following-sibling::{value_tag}[@class='{value_attrs['class']}']"
                elif 'data-testid' in value_attrs:
                    return f"following-sibling::{value_tag}[@data-testid='{value_attrs['data-testid']}']"
                else:
                    return f"following-sibling::{value_tag}[1]"
        except ValueError:
            pass
    
    # Pattern 2: Ancestor relationship (go up then search down)
    # Try different ancestor levels - STOP at first match (shortest path)
    for level in range(1, 11):
        try:
            ancestors = label_elem.xpath(f'ancestor::*[{level}]')
            if not ancestors:
                continue
            
            ancestor = ancestors[0]
            
            # Check if value_elem is a descendant of this ancestor
            descendants = ancestor.xpath(f'.//{value_tag}')
            
            if value_elem in descendants:
                # Found common ancestor - build descendant part with best attribute
                # Priority: data-testid > data-test-id > id > class
                if 'data-testid' in value_attrs:
                    descendant_part = f"//{value_tag}[@data-testid='{value_attrs['data-testid']}']"
                elif 'data-test-id' in value_attrs:
                    descendant_part = f"//{value_tag}[@data-test-id='{value_attrs['data-test-id']}']"
                elif 'id' in value_attrs:
                    descendant_part = f"//{value_tag}[@id='{value_attrs['id']}']"
                elif 'class' in value_attrs:
                    descendant_part = f"//{value_tag}[@class='{value_attrs['class']}']"
                else:
                    descendant_part = f"//{value_tag}"
                
                # IMPORTANT: Return immediately (shortest path wins)
                return f"ancestor::*[{level}]{descendant_part}"
        except:
            continue
    
    # Pattern 3: Table cells (common in forms)
    if label_tag == 'td' and value_tag == 'td':
        return f"following-sibling::td"
    
    return None


def build_row_relative_xpath(value_elem: html.HtmlElement) -> str:
    """
    Build a row‑relative XPath for a value element.
    This is used for fields that live in the grid row (outside the popup).
    The returned XPath is intended to be evaluated with the <tr> element as
    the context node, so it always starts with './/'.
    """
    value_tag = value_elem.tag
    value_attrs = dict(value_elem.attrib)

    # Start with a relative selector from the row context
    selector_parts = [f".//{value_tag}"]

    # Prefer stable attributes on the value cell so the XPath works across rows
    # and sessions (we avoid using the actual value text because that changes).
    if 'data-testid' in value_attrs:
        selector_parts.append(f"[@data-testid='{value_attrs['data-testid']}']")
    elif 'data-test-id' in value_attrs:
        selector_parts.append(f"[@data-test-id='{value_attrs['data-test-id']}']")
    elif 'id' in value_attrs and value_attrs['id']:
        selector_parts.append(f"[@id='{value_attrs['id']}']")
    elif 'class' in value_attrs and value_attrs['class']:
        # Use first class and match via contains() to be resilient to extra classes
        first_class = value_attrs['class'].split()[0]
        selector_parts.append(f"[contains(@class, '{first_class}')]")
    else:
        # Fallback: use positional index of this cell within its row for stability
        row = value_elem
        while row is not None and row.tag != 'tr':
            row = row.getparent()
        if row is not None:
            # Consider only element children with the same tag (td/th) in this row
            same_tag_children = [e for e in row if isinstance(e, html.HtmlElement) and e.tag == value_tag]
            try:
                index = same_tag_children.index(value_elem) + 1  # XPath is 1‑based
                selector_parts.append(f"[{index}]")
            except ValueError:
                # If for some reason we can't determine index, just use the tag alone
                pass

    return ''.join(selector_parts)


def build_xpath_pattern(tree: html.HtmlElement, label_elem: html.HtmlElement, 
                       relationship: str, popup_container: Optional[html.HtmlElement] = None) -> str:
    """
    Build a complete XPath pattern with {{LABEL}} placeholder.
    Uses most stable attributes available.
    
    Args:
        tree: Parsed HTML tree
        label_elem: The label element
        relationship: The relationship pattern from analyze_element_relationship
        popup_container: Optional popup container to scope the XPath to
    
    Returns:
        Complete XPath pattern with {{LABEL}} placeholder
    """
    label_tag = label_elem.tag
    label_attrs = dict(label_elem.attrib)
    
    # Build the label selector part
    label_selector_parts = [label_tag]
    
    # Add most stable attribute available (priority order)
    if 'class' in label_attrs:
        label_selector_parts.append(f"[@class='{label_attrs['class']}']")
    
    # IMPORTANT:
    # For robustness we avoid strict text()='...' matches because labels in EMRs
    # often include colons / extra spaces. Instead, we always use a normalized
    # contains() check so that a label like "Location of Service:" still matches
    # the logical label "Location of Service".
        label_selector_parts.append("[contains(normalize-space(.), '{{LABEL}}')]")
    
    label_selector = ''.join(label_selector_parts)
    
    # If popup was detected, scope the XPath to the popup container
    if popup_container:
        # Build popup container selector
        popup_tag = popup_container.tag
        popup_attrs = dict(popup_container.attrib)
        popup_selector_parts = [popup_tag]
        
        # Use most stable attribute for popup
        if 'id' in popup_attrs and popup_attrs['id']:
            popup_id = popup_attrs['id']
            # If ID looks dynamic (contains numbers/underscores), build a
            # starts-with condition so it works across sessions, e.g.:
            # id="view_sessions_notes_md_12345"  →  starts-with(@id, 'view_sessions_notes_md')
            if any(ch.isdigit() for ch in popup_id) or '_' in popup_id:
                parts = popup_id.split('_')
                if len(parts) > 1:
                    prefix = '_'.join(parts[:-1])
                    popup_selector_parts.append(f"[starts-with(@id, '{prefix}')]")
                else:
                    popup_selector_parts.append(f"[@id='{popup_id}']")
            else:
                popup_selector_parts.append(f"[@id='{popup_id}']")
        elif 'class' in popup_attrs:
            # Use first class if multiple classes exist
            first_class = popup_attrs['class'].split()[0] if popup_attrs['class'] else ''
            if first_class:
                popup_selector_parts.append(f"[contains(@class, '{first_class}')]")
        elif 'role' in popup_attrs:
            popup_selector_parts.append(f"[@role='{popup_attrs['role']}']")
        
        popup_selector = ''.join(popup_selector_parts)
        # Scope XPath to popup: //popup//label/relationship
        xpath_pattern = f"//{popup_selector}//{label_selector}/{relationship}"
    else:
        # Normal XPath (existing behavior)
        xpath_pattern = f"//{label_selector}/{relationship}"
    
    return xpath_pattern


def test_xpath_pattern(tree: html.HtmlElement, xpath_pattern: str, 
                       test_fields: Dict[str, str]) -> Tuple[int, int]:
    """
    Test an XPath pattern against multiple fields (case-insensitive).
    
    Args:
        tree: Parsed HTML tree
        xpath_pattern: XPath pattern with {{LABEL}} placeholder
        test_fields: Dict of {label: expected_value}
    
    Returns:
        Tuple of (successful_matches, total_fields)
    """
    successful = 0
    total = len(test_fields)
    
    for label, expected_value in test_fields.items():
        try:
            # Try with original label first
            test_xpath = xpath_pattern.replace('{{LABEL}}', label)
            results = tree.xpath(test_xpath)
            
            # If not found, try with different case variations
            if not results:
                # Try lowercase
                test_xpath = xpath_pattern.replace('{{LABEL}}', label.lower())
                results = tree.xpath(test_xpath)
            
            if not results:
                # Try title case
                test_xpath = xpath_pattern.replace('{{LABEL}}', label.title())
                results = tree.xpath(test_xpath)
            
            if results:
                # Get text content from result
                result_text = results[0].text_content().strip()
                expected_lower = expected_value.lower()
                result_lower = result_text.lower()
                
                # Check if it matches expected value (case-insensitive)
                if result_lower == expected_lower or expected_lower in result_lower:
                    successful += 1
        except Exception as e:
            # XPath execution failed, skip this field
            continue
    
    return successful, total


def generate_xpath_from_html(raw_html: str, field_data: Dict[str, Dict[str, str]]) -> Optional[str]:
    """
    Generate an XPath pattern by analyzing HTML structure and field data.
    
    Args:
        raw_html: The complete HTML content
        field_data: Dict of {field_key: {"value": "...", "label": "..."}}" 
                   Only include fields where value is not "Not found" or "Empty"
    
    Returns:
        XPath pattern with {{LABEL}} placeholder, or None if generation fails
    """
    if not field_data:
        return None
    
    # DEBUG: Check HTML state
    print(f"\n=== HTML DEBUG INFO ===")
    print(f"1. HTML size: {len(raw_html)} bytes")
    print(f"2. HTML first 500 chars: {raw_html[:500]}")
    print(f"3. 'service location' in HTML (case-insensitive): {'service location' in raw_html.lower()}")
    
    try:
        # Parse HTML with increased limits for large files
        parser = html.HTMLParser(huge_tree=True)
        tree = html.fromstring(raw_html, parser=parser)
        print(f"4. Tree type: {type(tree)}")
        print(f"5. Tree tag: {tree.tag}")
        print(f"======================\n")
    except Exception as e:
        print(f"Error parsing HTML: {e}")
        return None
    
    # Detect popup/modal container
    popup_container = detect_popup_container(tree)
    if popup_container:
        print(f"🎯 Popup detected! Scoping XPath generation to popup container only.")
    else:
        print(f"📄 No popup detected. Using full document scope (existing behavior).")
    
    # Filter out fields without valid values
    valid_fields = {
        data['label']: data['value'] 
        for data in field_data.values() 
        if data.get('value') and data.get('label') and 
           data['value'].lower() not in ['not found', 'empty', '']
    }
    
    if not valid_fields:
        return None
    
    # Try ALL fields and pick the best XPath pattern
    best_xpath = None
    best_success_rate = 0
    best_field = None
    
    print(f"\n🔍 Trying to generate XPath from {len(valid_fields)} valid fields...\n")
    
    for idx, (label, value) in enumerate(valid_fields.items(), 1):
        print(f"\n--- Attempt {idx}/{len(valid_fields)}: '{label}' = '{value}' ---")
        
        # Find label element (prefer deepest/most specific, scoped to popup if detected)
        label_elem = find_element_with_text(tree, label, exact=True, scope=popup_container)
        if label_elem is None:
            label_elem = find_element_with_text(tree, label, exact=False, scope=popup_container)
        
        if label_elem is None:
            print(f"❌ Could not find label element")
            continue
        
        print(f"✓ Found label: <{label_elem.tag}> with {len(label_elem.attrib)} attributes")
        
        # Find value element (scoped to popup if detected)
        value_elem = find_value_element_near_label(tree, label_elem, value, scope=popup_container)
        
        if value_elem is None:
            print(f"❌ Could not find value element")
            continue
        
        print(f"✓ Found value: <{value_elem.tag}>")
        
        # Analyze relationship
        relationship = analyze_element_relationship(tree, label_elem, value_elem)
        
        if not relationship:
            print(f"❌ Could not determine relationship")
            continue
        
        print(f"✓ Relationship: {relationship}")
        
        # Build XPath pattern
        xpath_pattern = build_xpath_pattern(tree, label_elem, relationship, popup_container)
        print(f"📋 Generated: {xpath_pattern}")
        
        # Test against ALL fields
        successful, total = test_xpath_pattern(tree, xpath_pattern, valid_fields)
        success_rate = successful / total if total > 0 else 0
        
        print(f"📊 Test results: {successful}/{total} ({success_rate:.1%})")
        
        # Track best pattern
        if success_rate > best_success_rate:
            best_success_rate = success_rate
            best_xpath = xpath_pattern
            best_field = label
            print(f"✨ NEW BEST PATTERN!")
        
        # If we found 100% match, use it immediately!
        if success_rate == 1.0:
            print(f"\n🎯 PERFECT! Found 100% match from field '{label}'")
            return xpath_pattern
        
        # If 90%+ match, very good - use it
        if success_rate >= 0.9:
            print(f"\n✅ Excellent match ({success_rate:.1%}) from field '{label}'")
            return xpath_pattern
    
    # Return best pattern if reasonable (>= 70%)
    if best_xpath and best_success_rate >= 0.7:
        print(f"\n✅ Using best pattern ({best_success_rate:.1%}) from field '{best_field}'")
        return best_xpath
    
    # Return even lower success if that's all we have (>= 50%)
    if best_xpath and best_success_rate >= 0.5:
        print(f"\n⚠️  Using best available pattern ({best_success_rate:.1%}) from field '{best_field}'")
        return best_xpath
    
    print(f"\n❌ Could not generate reliable XPath (best was {best_success_rate:.1%})")
    return None


def generate_xpath_for_all_fields(raw_html: str, field_data: Dict[str, Dict[str, str]]) -> Optional[Dict[str, Any]]:
    """
    Generate individual XPath patterns for each field.
    Returns a dict with XPath patterns and popup info.
    
    Args:
        raw_html: The complete HTML content
        field_data: Dict of {field_key: {"value": "...", "label": "..."}}" 
                   Only include fields where value is not "Not found" or "Empty"
    
    Returns:
        Dict with:
        - 'xpath_patterns': Dict of {label: xpath_pattern}
        - 'is_popup': Boolean indicating if popup was detected
        - 'popup_root_selector': CSS selector for popup (if popup detected)
        Or None if generation fails
    """
    if not field_data:
        return None
    
    print(f"\n=== Generating individual XPaths for {len(field_data)} fields ===")
    
    try:
        # Parse HTML with increased limits for large files
        parser = html.HTMLParser(huge_tree=True)
        tree = html.fromstring(raw_html, parser=parser)
    except Exception as e:
        print(f"Error parsing HTML: {e}")
        return None
    
    # Detect popup/modal container (dynamic detection)
    print(f"\n{'='*60}")
    print(f"🔍 DYNAMIC POPUP DETECTION STARTING")
    print(f"{'='*60}")
    
    # Extract field labels for smarter detection
    field_labels = [data.get('label', '') for data in field_data.values() if data.get('label')]
    
    popup_container = detect_popup_container(tree, field_labels=field_labels)
    if popup_container:
        print(f"\n🎯 Popup detected! Scoping XPath generation to popup container only.")
        print(f"   Popup element: <{popup_container.tag}>")
        print(f"   Class: {popup_container.get('class', 'N/A')}")
        print(f"   ID: {popup_container.get('id', 'N/A')}")
        print(f"   Role: {popup_container.get('role', 'N/A')}")
    else:
        print(f"\n📄 No popup detected. Using full document scope (existing behavior).")
    print(f"{'='*60}\n")
    
    # Filter out fields without valid values
    valid_fields: Dict[str, str] = {}
    for data in field_data.values():
        value = data.get('value')
        label = data.get('label')
        if not value or not label:
            continue
        if value.lower() in ['not found', 'empty', '']:
            continue
        valid_fields[label] = value
    
    if not valid_fields:
        return None
    
    # Generate XPath for each field individually
    xpath_patterns: Dict[str, str] = {}
    successful_count = 0
    failed_fields: Dict[str, str] = {}
    # total_fields counts only fields that are NOT in the ignored list, so
    # e.g. "Client" will never block all_valid from being True.
    total_fields = sum(
        1
        for label in valid_fields.keys()
        if normalize_text(label).rstrip(':') not in IGNORED_LABELS
    )
    
    for idx, (label, value) in enumerate(valid_fields.items(), 1):
        print(f"\n{'='*70}")
        print(f"--- Field {idx}/{len(valid_fields)}: '{label}' = '{value}' ---")
        print(f"{'='*70}")
        label_norm = normalize_text(label).rstrip(':')
        
        # NEW BEHAVIOR:
        # If a popup is detected we PREFER elements inside that popup, but we no
        # longer skip fields that live outside it (e.g. the row/grid under the
        # popup). For those, we fall back to full-document search so we can
        # still generate XPaths for columns like Date of Session, Time In, etc.
        label_elem = None
        label_in_popup = False

        if popup_container:
            print(f"   🎯 Popup mode: prefer popup container, allow fallback to full document")
            print(f"   Popup container: <{popup_container.tag}> id='{popup_container.get('id', 'N/A')}' class='{popup_container.get('class', 'N/A')}'")
            
            # 1) Try inside popup first
            label_elem = find_element_with_text(tree, label, exact=True, scope=popup_container)
            if label_elem is None:
                print(f"   → Trying contains match (not exact) inside popup...")
                label_elem = find_element_with_text(tree, label, exact=False, scope=popup_container)
            
            if label_elem is not None:
                # Confirm the label is actually a descendant of the popup
                current = label_elem
                while current is not None:
                    if current == popup_container:
                        label_in_popup = True
                        break
                    current = current.getparent()
                
                if not label_in_popup:
                    print(f"   ⚠️  WARNING: Label found but popup container not in ancestors - treating as outside popup")
            else:
                print(f"   ℹ️  Label '{label}' not found inside popup - will search full document")
        
        # 2) If not found in popup (or no popup), search entire document
        if label_elem is None:
            print(f"   📄 Searching entire document for label '{label}'")
            label_elem = find_element_with_text(tree, label, exact=True, scope=None)
            if label_elem is None:
                label_elem = find_element_with_text(tree, label, exact=False, scope=None)
        
        if label_elem is None:
            print(f"   ❌ Could not find label element for '{label}' anywhere in HTML")
            # Record as a failure unless this label is intentionally ignored
            if label_norm not in IGNORED_LABELS:
                failed_fields[label] = "Could not find label element in HTML"
            continue
        print(f"   ✅ Label found in document: <{label_elem.tag}> (inside popup: {label_in_popup})")

        # GENERIC PATTERN: label element followed immediately by a raw text node
        # that contains the value (e.g. "PROVIDER NAME:" <br> "WEIDER SHIMON").
        # In this case there is no dedicated value element, so we build a
        # text-node XPath that targets the following-sibling text()[1] of the
        # label element. This is dynamic and works for ANY label with that
        # structure, not just specific names.
        tail_raw = (label_elem.tail or "").strip()
        if tail_raw:
            tail_lower = tail_raw.lower()
            expected_lower = value.strip().lower()
            if expected_lower and expected_lower in tail_lower:
                print(f"   🎯 Detected label+text pattern for '{label}' (value in label tail)")

                # Build the label selector part
                label_tag = label_elem.tag
                label_attrs = dict(label_elem.attrib)
                label_selector_parts = [label_tag]
                if 'class' in label_attrs:
                    label_selector_parts.append(f"[@class='{label_attrs['class']}']")
                normalized_label = label.strip().rstrip(':')
                label_selector_parts.append(
                    f"[contains(normalize-space(.), '{normalized_label}')]"
                )
                label_selector = ''.join(label_selector_parts)

                # If we have a popup, scope to it; otherwise use document scope
                if popup_container:
                    popup_tag = popup_container.tag
                    popup_attrs = dict(popup_container.attrib)
                    popup_selector_parts = [popup_tag]
                    if 'id' in popup_attrs and popup_attrs['id']:
                        popup_id = popup_attrs['id']
                        if any(ch.isdigit() for ch in popup_id) or '_' in popup_id:
                            parts = popup_id.split('_')
                            if len(parts) > 1:
                                prefix = '_'.join(parts[:-1])
                                popup_selector_parts.append(f"[starts-with(@id, '{prefix}')]")
                            else:
                                popup_selector_parts.append(f"[@id='{popup_id}']")
                        else:
                            popup_selector_parts.append(f"[@id='{popup_id}']")
                    elif 'class' in popup_attrs:
                        first_class = popup_attrs['class'].split()[0] if popup_attrs['class'] else ''
                        if first_class:
                            popup_selector_parts.append(f"[contains(@class, '{first_class}')]")
                    elif 'role' in popup_attrs:
                        popup_selector_parts.append(f"[@role='{popup_attrs['role']}']")

                    popup_selector = ''.join(popup_selector_parts)
                    xpath = f"//{popup_selector}//{label_selector}/following-sibling::text()[1]"
                else:
                    xpath = f"//{label_selector}/following-sibling::text()[1]"

                # Save XPath without validation
                xpath_patterns[label] = xpath
                if label_norm not in IGNORED_LABELS:
                    successful_count += 1
                print(f"✅ Generated label+text XPath for '{label}': {xpath}")
                continue
        
        # Find value element:
        # - If label is inside popup, search inside popup (old behavior).
        # - If label is outside popup (grid row), search whole document.
        value_scope = popup_container if label_in_popup else None
        value_elem = find_value_element_near_label(tree, label_elem, value, scope=value_scope)
        
        # Generic fallback: sometimes a label text appears inside the popup
        # (e.g. in a long narrative) but the actual value we care about lives
        # only in the grid row (outside popup). In that case, if we fail to
        # find a value INSIDE the popup, we fall back to a full‑document
        # search and treat it as a non‑popup/grid field.
        if value_elem is None and popup_container and label_in_popup:
            print(f"   ⚠️  Value for '{label}' not found inside popup - falling back to full document search")
            label_in_popup = False
            value_scope = None
            value_elem = find_value_element_near_label(tree, label_elem, value, scope=value_scope)
        
        if value_elem is None:
            print(f"❌ Could not find value element for '{label}'")
            if label_norm not in IGNORED_LABELS:
                failed_fields[label] = "Could not find value element near label in HTML"
            continue
        
        # Analyze relationship
        relationship = analyze_element_relationship(tree, label_elem, value_elem)
        
        if not relationship:
            print(f"❌ Could not determine relationship for '{label}'")
            if label_norm not in IGNORED_LABELS:
                failed_fields[label] = "Could not determine structural relationship between label and value"
            continue
        
        # Decide how to build the final XPath:
        # - If the field is INSIDE the popup: scope to popup + use label relationship (old behavior).
        # - If the field is OUTSIDE the popup (row/grid): build a row‑relative XPath
        #   based on the value element only, to be evaluated from the clicked <tr>.
        # - If there is no popup at all: fall back to the original document‑level pattern.
        if popup_container and label_in_popup:
            # Build XPath pattern (with actual label, not {{LABEL}} placeholder)
            label_tag = label_elem.tag
            label_attrs = dict(label_elem.attrib)
            
            # Build the label selector part
            label_selector_parts = [label_tag]
            
            # Add most stable attribute available (priority order)
            if 'class' in label_attrs:
                label_selector_parts.append(f"[@class='{label_attrs['class']}']")
            
            # Use actual label text (not placeholder)
            # Use normalized contains() so labels like "Location of Service:" match
            # the logical label "Location of Service" that we store in the DB.
            normalized_label = label.strip().rstrip(':')
            label_selector_parts.append(
                f"[contains(normalize-space(.), '{normalized_label}')]"
            )
            
            label_selector = ''.join(label_selector_parts)
            
            # Build popup container selector
            popup_tag = popup_container.tag
            popup_attrs = dict(popup_container.attrib)
            popup_selector_parts = [popup_tag]
            
            # Use most stable attribute for popup
            if 'id' in popup_attrs and popup_attrs['id']:
                popup_id = popup_attrs['id']
                # If ID looks dynamic (contains numbers/underscores), build a
                # starts-with condition so it works across sessions, e.g.:
                # id="view_sessions_notes_md_12345"  →  starts-with(@id, 'view_sessions_notes_md')
                if any(ch.isdigit() for ch in popup_id) or '_' in popup_id:
                    parts = popup_id.split('_')
                    if len(parts) > 1:
                        prefix = '_'.join(parts[:-1])
                        popup_selector_parts.append(f"[starts-with(@id, '{prefix}')]")
                    else:
                        popup_selector_parts.append(f"[@id='{popup_id}']")
                else:
                    popup_selector_parts.append(f"[@id='{popup_id}']")
            elif 'class' in popup_attrs:
                # Use first class if multiple classes exist
                first_class = popup_attrs['class'].split()[0] if popup_attrs['class'] else ''
                if first_class:
                    popup_selector_parts.append(f"[contains(@class, '{first_class}')]")
            elif 'role' in popup_attrs:
                popup_selector_parts.append(f"[@role='{popup_attrs['role']}']")
            
            popup_selector = ''.join(popup_selector_parts)
            # Scope XPath to popup: //popup//label/relationship
            xpath = f"//{popup_selector}//{label_selector}/{relationship}"
            print(f"🎯 Popup-scoped XPath generated")
        elif popup_container and not label_in_popup:
            # Row/grid field: build a row‑relative XPath, to be evaluated with
            # the clicked <tr> as the context node in the extension.
            xpath = build_row_relative_xpath(value_elem)
            print(f"🧮 Row-scoped XPath generated: {xpath}")
        else:
            # No popup at all: use original document‑level pattern
            label_tag = label_elem.tag
            label_attrs = dict(label_elem.attrib)
            label_selector_parts = [label_tag]
            if 'class' in label_attrs:
                label_selector_parts.append(f"[@class='{label_attrs['class']}']")
            normalized_label = label.strip().rstrip(':')
            label_selector_parts.append(
                f"[contains(normalize-space(.), '{normalized_label}')]"
            )
            label_selector = ''.join(label_selector_parts)
            xpath = f"//{label_selector}/{relationship}"
        
        # Save XPath without validation
        xpath_patterns[label] = xpath
        # Only count non-ignored labels
        if label_norm not in IGNORED_LABELS:
            successful_count += 1
        print(f"✅ Generated XPath for '{label}': {xpath}")
    
    if successful_count == 0:
        print(f"\n❌ Could not generate any XPath patterns")
        return None
    
    print(f"\n✅ Successfully generated {successful_count}/{len(valid_fields)} XPath patterns")
    
    # Return XPath patterns along with popup info
    result: Dict[str, Any] = {
        'xpath_patterns': xpath_patterns,
        'is_popup': popup_container is not None,
        'popup_root_selector': generate_popup_css_selector(popup_container) if popup_container else None,
        'total_fields': total_fields,
        'successful_fields': successful_count,
    }
    
    if popup_container:
        print(f"🎯 Popup detected - CSS selector: {result['popup_root_selector']}")
    
    return result
