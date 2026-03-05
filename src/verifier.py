from .taxonomy import classify_result

class Verifier:
    def verify(self, result: dict) -> dict:
        return classify_result(result)
