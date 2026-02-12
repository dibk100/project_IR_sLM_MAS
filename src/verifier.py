from .taxonomy import classify_result

"""
B-v2에서 사용하는 verifier.py
"""

class Verifier:
    def verify(self, result: dict) -> dict:
        return classify_result(result)
