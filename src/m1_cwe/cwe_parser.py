#!/usr/bin/env python3
import xml.etree.ElementTree as ET
import json
import argparse
import sys
import os

from src.common.lang_utils import get_cwe_aliases, CWE_ALIASES

def setup_args():
    parser = argparse.ArgumentParser(description="CWE-699 XML Catalog Parser & Pruner")
    parser.add_argument("--cwe", required=True, help="Path to CWE XML file (e.g. 699.xml)")
    parser.add_argument("--lang", default="cpp",
                        help="Target codebase language (known: cpp/java/python/go/js/all; "
                             "unknown languages degrade to language-independent weaknesses only)")
    parser.add_argument("--project", default=None, help="Target project (to write catalog into <project>/.audit_workspace/catalog.json)")
    parser.add_argument("--output", default=None, help="Output JSON path (default: <project>/.audit_workspace/catalog.json)")
    return parser.parse_args()

def get_language_aliases(lang):
    norm_aliases = get_cwe_aliases(lang)
    if lang.lower() not in CWE_ALIASES and lang != "all":
        # 未知语言(如 rust/php/swift/ruby)不再硬拒:与 explorer/detect_language 的宽容降级对齐,
        # 仅保留"非语言特定 / 语言无关"的弱点,并显式告警(风格同 explorer.py 的未知语言提示)。
        known = "/".join(CWE_ALIASES.keys())
        print(f"[!] Unknown --lang '{lang}': retaining only language-independent weaknesses. "
              f"Known languages: {known}.", file=sys.stderr)
    return norm_aliases


def parse_xml(xml_path, target_lang):
    if not os.path.exists(xml_path):
        print(f"Error: XML file not found at {xml_path}", file=sys.stderr)
        sys.exit(1)
        
    print(f"Parsing CWE XML: {xml_path} for target language: {target_lang}")
    tree = ET.parse(xml_path)
    root = tree.getroot()
    
    # Mitre CWE XML namespace
    ns = {'ns': 'http://cwe.mitre.org/cwe-7'}
    
    language_aliases = get_language_aliases(target_lang) if target_lang != "all" else []
    catalog = {}
    
    for weakness in root.findall('.//ns:Weakness', ns):
        w_id = weakness.attrib.get('ID')
        name = weakness.attrib.get('Name')
        status = weakness.attrib.get('Status')
        
        # Check platforms / languages
        languages = []
        platform_languages = weakness.findall('.//ns:Language', ns)
        for pl in platform_languages:
            lang_class = pl.attrib.get('Class')
            if lang_class:
                languages.append(lang_class)
                
        # If languages are defined, verify compatibility
        if target_lang != "all" and languages:
            is_compatible = any(la in languages for la in language_aliases)
            if not is_compatible:
                continue # Skip this weakness as it doesn't apply to the target language
        
        # Descriptions
        desc_el = weakness.find('ns:Description', ns)
        desc = desc_el.text.strip() if (desc_el is not None and desc_el.text) else ""
        
        extended_desc_el = weakness.find('ns:Extended_Description', ns)
        ext_desc = ""
        if extended_desc_el is not None:
            paragraphs = [p.text.strip() for p in extended_desc_el.findall('.//ns:p', ns) if p.text]
            if not paragraphs:
                ext_desc = extended_desc_el.text.strip() if extended_desc_el.text else ""
            else:
                ext_desc = "\n".join(paragraphs)
                
        # Consequences
        consequences = []
        for cons in weakness.findall('.//ns:Consequence', ns):
            scopes = [s.text.strip() for s in cons.findall('ns:Scope', ns) if s.text]
            impacts = [i.text.strip() for i in cons.findall('ns:Impact', ns) if i.text]
            notes_el = cons.find('ns:Note', ns)
            note = notes_el.text.strip() if (notes_el is not None and notes_el.text) else ""
            
            consequences.append({
                "scopes": scopes,
                "impacts": impacts,
                "note": note
            })

        # Demonstrative examples
        bad_examples = []
        for ex in weakness.findall('.//ns:Demonstrative_Example', ns):
            intro_el = ex.find('ns:Intro_Text', ns)
            intro = "".join(intro_el.itertext()).strip() if intro_el is not None else ""
            for code_el in ex.findall('ns:Example_Code', ns):
                if code_el.attrib.get('Nature') != 'Bad':
                    continue
                code = "".join(code_el.itertext()).strip()
                if code:
                    bad_examples.append({
                        "language": code_el.attrib.get('Language', ''),
                        "intro": intro,
                        "code": code
                    })

        # Observed examples
        observed = []
        for obs in weakness.findall('.//ns:Observed_Example', ns):
            ref_el = obs.find('ns:Reference', ns)
            desc_el = obs.find('ns:Description', ns)
            observed.append({
                "cve": ref_el.text.strip() if (ref_el is not None and ref_el.text) else "",
                "description": desc_el.text.strip() if (desc_el is not None and desc_el.text) else ""
            })

        # Potential mitigations
        mitigations = []
        for mit in weakness.findall('.//ns:Mitigation', ns):
            phase_el = mit.find('ns:Phase', ns)
            mdesc_el = mit.find('ns:Description', ns)
            mdesc = "".join(mdesc_el.itertext()).strip() if mdesc_el is not None else ""
            if mdesc:
                mitigations.append({
                    "phase": phase_el.text.strip() if (phase_el is not None and phase_el.text) else "",
                    "description": mdesc
                })

        catalog[w_id] = {
            "id": w_id,
            "name": name,
            "description": desc,
            "extended_description": ext_desc,
            "consequences": consequences,
            "languages": languages if languages else ["Language-Independent"],
            "demonstrative_examples": bad_examples,
            "observed_examples": observed,
            "potential_mitigations": mitigations
        }
        
    print(f"Extraction completed. Retained {len(catalog)} weaknesses applicable to {target_lang}.")
    return catalog

def main():
    args = setup_args()
    catalog = parse_xml(args.cwe, args.lang)

    output = args.output
    if not output:
        if not args.project:
            print("Error: need --output, or --project to derive default workspace path.", file=sys.stderr)
            sys.exit(1)
        from src.common import paths
        output = paths.catalog_path(args.project)

    output_dir = os.path.dirname(output)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    with open(output, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)
    print(f"Saved catalog to: {output}")
    
    # Print machine-readable single-line JSON at the very end of stdout
    print(json.dumps({"catalog": os.path.abspath(output), "weaknesses": len(catalog)}, ensure_ascii=False))

if __name__ == "__main__":
    main()

