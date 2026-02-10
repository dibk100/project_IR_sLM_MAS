from .taxonomy import classify_error, ErrorType

class Verifier:
    def verify(self, result: dict) -> dict:
        """
        Analyzes the execution result and adds 'success', 'error_type', 'signature' fields.
        """
        stderr = result.get("stderr", "")
        stdout = result.get("stdout", "")
        returncode = result.get("returncode", 1)
        timeout = result.get("timeout", False)
        
        error_type, signature = classify_error(stderr, stdout, returncode, timeout)
        
        return {
            "success": error_type == ErrorType.PASS.value,
            "error_type": error_type,
            "signature": signature
        }
