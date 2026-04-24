"""
search_engine.py — Motor de busca de veículos com fallback progressivo.
Extraído de main.py para isolar a lógica de busca em um módulo reutilizável.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Any, Tuple

from unidecode import unidecode
from rapidfuzz import fuzz

from vehicle_mappings import MAPEAMENTO_CATEGORIAS, MAPEAMENTO_MOTOS


# ─── Fallback priority ────────────────────────────────────────────────────────

FALLBACK_PRIORITY = [
    "motor",
    "portas",
    "cor",
    "combustivel",
    "opcionais",
    "cambio",
    "KmMax",
    "AnoMax",
    "modelo",
    "marca",
    "categoria",
]


# ─── Result dataclass ─────────────────────────────────────────────────────────


@dataclass
class SearchResult:
    vehicles: List[Dict[str, Any]]
    total_found: int
    fallback_info: Dict[str, Any]
    removed_filters: List[str]


# ─── Search engine ────────────────────────────────────────────────────────────


class VehicleSearchEngine:
    def __init__(self):
        self.exact_fields = ["tipo", "marca", "cambio", "motor", "portas"]

    def _any_csv_value_matches(self, raw_val, field_val, vehicle_type, word_matcher):
        if not raw_val:
            return False
        for val in self.split_multi_value(raw_val):
            words = val.split()
            ok, _ = word_matcher(words, field_val, vehicle_type)
            if ok:
                return True
        return False

    def normalize_text(self, text: str) -> str:
        if not text:
            return ""
        return unidecode(str(text)).lower().replace("-", "").replace(" ", "").strip()

    def convert_price(self, price_str: Any) -> Optional[float]:
        if not price_str:
            return None
        try:
            if isinstance(price_str, (int, float)):
                return float(price_str)
            cleaned = str(price_str).replace(",", "").replace("R$", "").replace(".", "").strip()
            return float(cleaned) / 100 if len(cleaned) > 2 else float(cleaned)
        except (ValueError, TypeError):
            return None

    def convert_year(self, year_str: Any) -> Optional[int]:
        if not year_str:
            return None
        try:
            return int(str(year_str).strip().replace("\n", "").replace("\r", "").replace(" ", ""))
        except (ValueError, TypeError):
            return None

    def convert_km(self, km_str: Any) -> Optional[int]:
        if not km_str:
            return None
        try:
            return int(str(km_str).replace(".", "").replace(",", "").strip())
        except (ValueError, TypeError):
            return None

    def convert_cc(self, cc_str: Any) -> Optional[float]:
        if not cc_str:
            return None
        try:
            if isinstance(cc_str, (int, float)):
                return float(cc_str)
            cleaned = str(cc_str).replace(",", ".").replace("L", "").replace("l", "").strip()
            value = float(cleaned)
            return value * 1000 if value < 10 else value
        except (ValueError, TypeError):
            return None

    def get_max_value_from_range_param(self, param_value: str) -> str:
        if not param_value:
            return param_value
        if "," in param_value:
            try:
                values = [float(v.strip()) for v in param_value.split(",") if v.strip()]
                if values:
                    return str(max(values))
            except (ValueError, TypeError):
                pass
        return param_value

    def find_category_by_model(self, model: str) -> Optional[str]:
        if not model:
            return None
        normalized_model = self.normalize_text(model)
        if normalized_model in MAPEAMENTO_MOTOS:
            _, category = MAPEAMENTO_MOTOS[normalized_model]
            return category
        model_words = normalized_model.split()
        for word in model_words:
            if len(word) >= 3 and word in MAPEAMENTO_MOTOS:
                _, category = MAPEAMENTO_MOTOS[word]
                return category
        for key, (_, category) in MAPEAMENTO_MOTOS.items():
            if key in normalized_model or normalized_model in key:
                return category
        if normalized_model in MAPEAMENTO_CATEGORIAS:
            return MAPEAMENTO_CATEGORIAS[normalized_model]
        for word in model_words:
            if len(word) >= 3 and word in MAPEAMENTO_CATEGORIAS:
                return MAPEAMENTO_CATEGORIAS[word]
        for key, category in MAPEAMENTO_CATEGORIAS.items():
            if key in normalized_model or normalized_model in key:
                return category
        return None

    def exact_match(self, query_words, field_content, *args) -> Tuple[bool, str]:
        if not query_words or not field_content:
            return False, "empty_input"
        normalized_content = self.normalize_text(field_content)
        for word in query_words:
            normalized_word = self.normalize_text(word)
            if len(normalized_word) < 2:
                continue
            if normalized_word not in normalized_content:
                return False, f"exact_miss: '{normalized_word}' não encontrado"
        return True, "exact_match: todas as palavras encontradas"

    def _fuzzy_match_all_words(self, query_words, field_content, fuzzy_threshold) -> Tuple[bool, str]:
        normalized_content = self.normalize_text(field_content)
        matched_words = []
        match_details = []
        for word in query_words:
            normalized_word = self.normalize_text(word)
            if len(normalized_word) < 2:
                continue
            word_matched = False
            if normalized_word in normalized_content:
                matched_words.append(normalized_word)
                match_details.append(f"exact:{normalized_word}")
                word_matched = True
            if not word_matched:
                for content_word in normalized_content.split():
                    if content_word.startswith(normalized_word):
                        matched_words.append(normalized_word)
                        match_details.append(f"starts_with:{normalized_word}")
                        word_matched = True
                        break
            if not word_matched and len(normalized_word) >= 3:
                for content_word in normalized_content.split():
                    if normalized_word in content_word:
                        matched_words.append(normalized_word)
                        match_details.append(f"substring:{normalized_word}>{content_word}")
                        word_matched = True
                        break
            if not word_matched and len(normalized_word) >= 3:
                max_score = max(fuzz.partial_ratio(normalized_content, normalized_word), fuzz.ratio(normalized_content, normalized_word))
                if max_score >= fuzzy_threshold:
                    matched_words.append(normalized_word)
                    match_details.append(f"fuzzy:{normalized_word}({max_score})")
                    word_matched = True
            if not word_matched:
                return False, f"moto_strict: palavra '{normalized_word}' não encontrada"
        if len(matched_words) >= len([w for w in query_words if len(self.normalize_text(w)) >= 2]):
            return True, f"moto_all_match: {', '.join(match_details)}"
        return False, "moto_strict: nem todas as palavras encontradas"

    def _fuzzy_match_any_word(self, query_words, field_content, fuzzy_threshold) -> Tuple[bool, str]:
        normalized_content = self.normalize_text(field_content)
        for word in query_words:
            normalized_word = self.normalize_text(word)
            if len(normalized_word) < 2:
                continue
            if normalized_word in normalized_content:
                return True, f"exact_match: {normalized_word}"
            for content_word in normalized_content.split():
                if content_word.startswith(normalized_word):
                    return True, f"starts_with_match: {normalized_word}"
            if len(normalized_word) >= 3:
                for content_word in normalized_content.split():
                    if normalized_word in content_word:
                        return True, f"substring_match: {normalized_word} in {content_word}"
                max_score = max(fuzz.partial_ratio(normalized_content, normalized_word), fuzz.ratio(normalized_content, normalized_word))
                if max_score >= fuzzy_threshold:
                    return True, f"fuzzy_match: {max_score}"
        return False, "no_match"

    def fuzzy_match(self, query_words, field_content, vehicle_type=None) -> Tuple[bool, str]:
        if not query_words or not field_content:
            return False, "empty_input"
        fuzzy_threshold = 98 if vehicle_type == "moto" else 90
        if vehicle_type == "moto":
            return self._fuzzy_match_all_words(query_words, field_content, fuzzy_threshold)
        else:
            return self._fuzzy_match_any_word(query_words, field_content, fuzzy_threshold)

    def model_match(self, query_words, field_content, vehicle_type=None) -> Tuple[bool, str]:
        exact_result, exact_reason = self.exact_match(query_words, field_content)
        if exact_result:
            return True, f"EXACT: {exact_reason}"
        fuzzy_result, fuzzy_reason = self.fuzzy_match(query_words, field_content, vehicle_type)
        if fuzzy_result:
            return True, f"FUZZY: {fuzzy_reason}"
        return False, f"NO_MATCH: exact({exact_reason}) + fuzzy({fuzzy_reason})"

    def split_multi_value(self, value: str) -> List[str]:
        if not value:
            return []
        return [v.strip() for v in str(value).split(",") if v.strip()]

    def apply_filters(self, vehicles, filters) -> List[Dict]:
        if not filters:
            return vehicles
        filtered_vehicles = list(vehicles)
        for filter_key, filter_value in filters.items():
            if not filter_value or not filtered_vehicles:
                continue
            if filter_key == "modelo":
                def matches(v, fv=filter_value):
                    vt = v.get("tipo", "")
                    for field in ["modelo", "titulo", "versao"]:
                        if self._any_csv_value_matches(fv, str(v.get(field, "")), vt, self.model_match):
                            return True
                    return False
                filtered_vehicles = [v for v in filtered_vehicles if matches(v)]
            elif filter_key in ["cor", "categoria", "opcionais", "combustivel"]:
                def matches(v, fk=filter_key, fv=filter_value):
                    return self._any_csv_value_matches(fv, str(v.get(fk, "")), v.get("tipo", ""), self.fuzzy_match)
                filtered_vehicles = [v for v in filtered_vehicles if matches(v)]
            elif filter_key in self.exact_fields:
                normalized_vals = [self.normalize_text(v) for v in self.split_multi_value(filter_value)]
                filtered_vehicles = [v for v in filtered_vehicles if self.normalize_text(str(v.get(filter_key, ""))) in normalized_vals]
        return filtered_vehicles

    def apply_range_filters(self, vehicles, valormax, anomax, kmmax, ccmax) -> List[Dict]:
        filtered_vehicles = list(vehicles)
        if anomax:
            try:
                max_year = int(anomax)
                filtered_vehicles = [v for v in filtered_vehicles if self.convert_year(v.get("ano")) is not None and self.convert_year(v.get("ano")) <= max_year]
            except ValueError:
                pass
        if kmmax:
            try:
                max_km = int(kmmax)
                filtered_vehicles = [v for v in filtered_vehicles if self.convert_km(v.get("km")) is not None and self.convert_km(v.get("km")) <= max_km]
            except ValueError:
                pass
        return filtered_vehicles

    def sort_vehicles(self, vehicles, valormax, anomax, kmmax, ccmax) -> List[Dict]:
        if not vehicles:
            return vehicles
        if ccmax:
            try:
                target_cc = float(ccmax)
                if target_cc < 10:
                    target_cc *= 1000
                return sorted(vehicles, key=lambda v: abs((self.convert_cc(v.get("cilindrada")) or 0) - target_cc))
            except ValueError:
                pass
        if valormax:
            try:
                target_price = float(valormax)
                return sorted(vehicles, key=lambda v: abs((self.convert_price(v.get("preco")) or 0) - target_price))
            except ValueError:
                pass
        if kmmax:
            return sorted(vehicles, key=lambda v: self.convert_km(v.get("km")) or float("inf"))
        if anomax:
            return sorted(vehicles, key=lambda v: self.convert_year(v.get("ano")) or 0, reverse=True)
        return sorted(vehicles, key=lambda v: self.convert_price(v.get("preco")) or 0, reverse=True)

    def search_with_fallback(self, vehicles, filters, valormax, anomax, kmmax, ccmax, excluded_ids) -> SearchResult:
        filtered_vehicles = self.apply_filters(vehicles, filters)
        filtered_vehicles = self.apply_range_filters(filtered_vehicles, valormax, anomax, kmmax, ccmax)
        if excluded_ids:
            filtered_vehicles = [v for v in filtered_vehicles if str(v.get("id")) not in excluded_ids]
        if filtered_vehicles:
            sorted_vehicles = self.sort_vehicles(filtered_vehicles, valormax, anomax, kmmax, ccmax)
            return SearchResult(vehicles=sorted_vehicles[:6], total_found=len(sorted_vehicles), fallback_info={}, removed_filters=[])

        current_filters = dict(filters)
        removed_filters = []
        current_valormax = valormax
        current_anomax = anomax
        current_kmmax = kmmax
        current_ccmax = ccmax

        for filter_to_remove in FALLBACK_PRIORITY:
            if filter_to_remove == "KmMax" and current_kmmax:
                test_vehicles = self.apply_filters(vehicles, current_filters)
                ok = [v for v in test_vehicles if self.convert_km(v.get("km")) is not None and self.convert_km(v.get("km")) <= int(current_kmmax)]
                if not ok:
                    current_kmmax = None
                    removed_filters.append("KmMax")
                else:
                    continue
            elif filter_to_remove == "AnoMax" and current_anomax:
                test_vehicles = self.apply_filters(vehicles, current_filters)
                ok = [v for v in test_vehicles if self.convert_year(v.get("ano")) is not None and self.convert_year(v.get("ano")) <= int(current_anomax)]
                if not ok:
                    current_anomax = None
                    removed_filters.append("AnoMax")
                else:
                    continue
            elif filter_to_remove == "modelo" and filter_to_remove in current_filters:
                model_value = current_filters["modelo"]
                if "categoria" not in current_filters or not current_filters["categoria"]:
                    mapped_category = self.find_category_by_model(model_value)
                    if mapped_category:
                        current_filters = {k: v for k, v in current_filters.items() if k != "modelo"}
                        current_filters["categoria"] = mapped_category
                        removed_filters.append(f"modelo({model_value})->categoria({mapped_category})")
                        filtered_vehicles = self.apply_filters(vehicles, current_filters)
                        filtered_vehicles = self.apply_range_filters(filtered_vehicles, current_valormax, current_anomax, current_kmmax, current_ccmax)
                        if excluded_ids:
                            filtered_vehicles = [v for v in filtered_vehicles if str(v.get("id")) not in excluded_ids]
                        if filtered_vehicles:
                            sorted_vehicles = self.sort_vehicles(filtered_vehicles, current_valormax, current_anomax, current_kmmax, current_ccmax)
                            return SearchResult(vehicles=sorted_vehicles[:6], total_found=len(sorted_vehicles), fallback_info={"fallback": {"removed_filters": removed_filters}}, removed_filters=removed_filters)
                    else:
                        current_filters = {k: v for k, v in current_filters.items() if k != "modelo"}
                        removed_filters.append(f"modelo({model_value})")
                else:
                    current_filters = {k: v for k, v in current_filters.items() if k != "modelo"}
                    removed_filters.append(f"modelo({model_value})")
            elif filter_to_remove in current_filters:
                current_filters = {k: v for k, v in current_filters.items() if k != filter_to_remove}
                removed_filters.append(filter_to_remove)
            else:
                continue

            filtered_vehicles = self.apply_filters(vehicles, current_filters)
            filtered_vehicles = self.apply_range_filters(filtered_vehicles, current_valormax, current_anomax, current_kmmax, current_ccmax)
            if excluded_ids:
                filtered_vehicles = [v for v in filtered_vehicles if str(v.get("id")) not in excluded_ids]
            if filtered_vehicles:
                sorted_vehicles = self.sort_vehicles(filtered_vehicles, current_valormax, current_anomax, current_kmmax, current_ccmax)
                return SearchResult(vehicles=sorted_vehicles[:6], total_found=len(sorted_vehicles), fallback_info={"fallback": {"removed_filters": removed_filters}}, removed_filters=removed_filters)

        return SearchResult(vehicles=[], total_found=0, fallback_info={}, removed_filters=removed_filters)
