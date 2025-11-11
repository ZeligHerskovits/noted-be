"""
XPath Generator Utility

This module analyzes HTML structure to automatically generate XPath patterns
that can extract field values based on their labels.
"""

from lxml import html, etree
from typing import Dict, List, Optional, Tuple
import re


def normalize_text(text: str) -> str:
    """Normalize text for comparison (remove extra whitespace, lowercase)"""
    if not text:
        return ""
    return ' '.join(text.strip().split()).lower()


def find_element_with_text(tree: html.HtmlElement, text: str, exact: bool = True) -> Optional[html.HtmlElement]:
    """
    Find the DEEPEST (most specific) element containing text (case-insensitive).
    Prefers elements with less nested content.
    
    Args:
        tree: Parsed HTML tree
        text: Text to search for
        exact: If True, match exact text; if False, match contains
    
    Returns:
        Most specific matching element or None
    """
    text_lower = text.lower()
    all_elements = tree.xpath("//*")
    
    matches = []
    
    for elem in all_elements:
        elem_text = elem.text_content().strip()
        if not elem_text:
            continue
            
        elem_text_lower = elem_text.lower()
        
        if exact and elem_text_lower == text_lower:
            matches.append(elem)
        elif not exact and text_lower in elem_text_lower:
            matches.append(elem)
    
    if not matches:
        return None
    
    # Find the DEEPEST element (most specific)
    # Priority: 1) Leaf nodes (no children), 2) Smallest text content
    # This prefers <span>Text</span> over <label><span>Text</span></label>
    
    # First try to find leaf nodes (elements with no child elements)
    leaf_matches = [e for e in matches if len(e) == 0]
    
    if leaf_matches:
        # Among leaf nodes, pick the one with smallest text
        deepest = min(leaf_matches, key=lambda e: len(e.text_content()))
    else:
        # No leaf nodes, pick element with smallest text content
        deepest = min(matches, key=lambda e: len(e.text_content()))
    
    return deepest


def find_value_element_near_label(tree: html.HtmlElement, label_elem: html.HtmlElement, 
                                   expected_value: str) -> Optional[html.HtmlElement]:
    """
    Find the MOST SPECIFIC element containing the value near a label element (case-insensitive).
    Prefers deepest/smallest elements with stable attributes.
    
    Args:
        tree: Parsed HTML tree
        label_elem: The label element
        expected_value: The expected value text to find
    
    Returns:
        Most specific element containing the value or None
    """
    expected_value_lower = expected_value.strip().lower()
    
    # Get ALL elements (not just those with direct text)
    all_elements = tree.xpath("//*")
    
    # Collect all near matches, don't return first one
    near_matches = []
    
    for val_elem in all_elements:
        elem_text = val_elem.text_content().strip()
        
        if not elem_text:  # Skip empty elements
            continue
            
        elem_text_lower = elem_text.lower()
        
        # Check for exact match or contains match (case-insensitive)
        if elem_text_lower == expected_value_lower or expected_value_lower in elem_text_lower:
            # Check if it's reasonably close to the label
            if is_element_near(label_elem, val_elem):
                near_matches.append(val_elem)
    
    if not near_matches:
        return None
    
    # Find the MOST SPECIFIC element among near matches
    # Priority:
    # 1. Elements with data-testid or data-test-id (most stable)
    # 2. Leaf nodes (no children)
    # 3. Smallest text content
    
    # First, prefer elements with stable test attributes
    stable_matches = [e for e in near_matches if 'data-testid' in e.attrib or 'data-test-id' in e.attrib]
    if stable_matches:
        # Among stable elements, prefer leaf nodes
        stable_leaf = [e for e in stable_matches if len(e) == 0]
        if stable_leaf:
            return min(stable_leaf, key=lambda e: len(e.text_content()))
        return min(stable_matches, key=lambda e: len(e.text_content()))
    
    # No stable attributes, prefer leaf nodes
    leaf_matches = [e for e in near_matches if len(e) == 0]
    if leaf_matches:
        return min(leaf_matches, key=lambda e: len(e.text_content()))
    
    # Fall back to smallest text content
    return min(near_matches, key=lambda e: len(e.text_content()))


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


def build_xpath_pattern(tree: html.HtmlElement, label_elem: html.HtmlElement, 
                       relationship: str) -> str:
    """
    Build a complete XPath pattern with {{LABEL}} placeholder.
    Uses most stable attributes available.
    
    Args:
        tree: Parsed HTML tree
        label_elem: The label element
        relationship: The relationship pattern from analyze_element_relationship
    
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
    
    # Use text()= for exact match if element has direct text, otherwise use contains(.)
    if label_elem.text and label_elem.text.strip():
        # Element has direct text (not just in children)
        label_selector_parts.append("[text()='{{LABEL}}']")
    else:
        # Text is in nested children - use contains
        label_selector_parts.append("[contains(normalize-space(.), '{{LABEL}}')]")
    
    label_selector = ''.join(label_selector_parts)
    
    # Combine with relationship
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
        
        # Find label element (prefer deepest/most specific)
        label_elem = find_element_with_text(tree, label, exact=True)
        if label_elem is None:
            label_elem = find_element_with_text(tree, label, exact=False)
        
        if label_elem is None:
            print(f"❌ Could not find label element")
            continue
        
        print(f"✓ Found label: <{label_elem.tag}> with {len(label_elem.attrib)} attributes")
        
        # Find value element
        value_elem = find_value_element_near_label(tree, label_elem, value)
        
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
        xpath_pattern = build_xpath_pattern(tree, label_elem, relationship)
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


def generate_xpath_for_all_fields(raw_html: str, field_data: Dict[str, Dict[str, str]]) -> Optional[Dict[str, str]]:
    """
    Generate individual XPath patterns for each field.
    Returns a dict mapping field labels to their specific XPath patterns.
    
    Args:
        raw_html: The complete HTML content
        field_data: Dict of {field_key: {"value": "...", "label": "..."}}" 
                   Only include fields where value is not "Not found" or "Empty"
    
    Returns:
        Dict of {label: xpath_pattern}, or None if generation fails
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
    
    # Filter out fields without valid values
    valid_fields = {
        data['label']: data['value'] 
        for data in field_data.values() 
        if data.get('value') and data.get('label') and 
           data['value'].lower() not in ['not found', 'empty', '']
    }
    
    if not valid_fields:
        return None
    
    # Generate XPath for each field individually
    xpath_patterns = {}
    successful_count = 0
    
    for idx, (label, value) in enumerate(valid_fields.items(), 1):
        print(f"\n--- Field {idx}/{len(valid_fields)}: '{label}' ---")
        
        # Find label element
        label_elem = find_element_with_text(tree, label, exact=True)
        if label_elem is None:
            label_elem = find_element_with_text(tree, label, exact=False)
        
        if label_elem is None:
            print(f"❌ Could not find label element for '{label}'")
            continue
        
        # Find value element
        value_elem = find_value_element_near_label(tree, label_elem, value)
        
        if value_elem is None:
            print(f"❌ Could not find value element for '{label}'")
            continue
        
        # Analyze relationship
        relationship = analyze_element_relationship(tree, label_elem, value_elem)
        
        if not relationship:
            print(f"❌ Could not determine relationship for '{label}'")
            continue
        
        # Build XPath pattern (with actual label, not {{LABEL}} placeholder)
        label_tag = label_elem.tag
        label_attrs = dict(label_elem.attrib)
        
        # Build the label selector part
        label_selector_parts = [label_tag]
        
        # Add most stable attribute available (priority order)
        if 'class' in label_attrs:
            label_selector_parts.append(f"[@class='{label_attrs['class']}']")
        
        # Use actual label text (not placeholder)
        if label_elem.text and label_elem.text.strip():
            label_selector_parts.append(f"[text()='{label}']")
        else:
            label_selector_parts.append(f"[contains(normalize-space(.), '{label}')]")
        
        label_selector = ''.join(label_selector_parts)
        xpath = f"//{label_selector}/{relationship}"
        
        xpath_patterns[label] = xpath
        successful_count += 1
        print(f"✅ Generated XPath for '{label}': {xpath}")
    
    if successful_count == 0:
        print(f"\n❌ Could not generate any XPath patterns")
        return None
    
    print(f"\n✅ Successfully generated {successful_count}/{len(valid_fields)} XPath patterns")
    return xpath_patterns
