from enum import Enum
import re

class ErrorType(Enum):
    PASS = "PASS"
    SYNTAX_ERROR = "SYNTAX_ERROR"
    NAME_ERROR = "NAME_ERROR"
    IMPORT_ERROR = "IMPORT_ERROR"
    TYPE_ERROR = "TYPE_ERROR"
    ATTRIBUTE_ERROR = "ATTRIBUTE_ERROR"
    ASSERTION_FAIL = "ASSERTION_FAIL"
    TIMEOUT = "TIMEOUT"
    OTHER_RUNTIME = "OTHER_RUNTIME"

def classify_error(stderr: str, stdout: str, returncode: int, timeout: bool = False) -> tuple[str, str]:
    """
    Classifies the error based on stderr/stdout and return code.
    Returns (error_type_str, signature_str).
    """
    if timeout:
        return ErrorType.TIMEOUT.value, "timeout"
    
    if returncode == 0:
        return ErrorType.PASS.value, "success"

    # Combine stdout and stderr for analysis, though stderr usually has the traceback
    full_log = (stderr or "") + "\n" + (stdout or "")

    if "SyntaxError" in full_log:
        return ErrorType.SYNTAX_ERROR.value, _extract_signature(full_log, "SyntaxError")
    if "NameError" in full_log:
        return ErrorType.NAME_ERROR.value, _extract_signature(full_log, "NameError")
    if "ModuleNotFoundError" in full_log or "ImportError" in full_log:
        return ErrorType.IMPORT_ERROR.value, _extract_signature(full_log, "ImportError")
    if "TypeError" in full_log:
        return ErrorType.TYPE_ERROR.value, _extract_signature(full_log, "TypeError")
    if "AttributeError" in full_log:
        return ErrorType.ATTRIBUTE_ERROR.value, _extract_signature(full_log, "AttributeError")
    if "AssertionError" in full_log or "FAIL" in full_log or "FAILED" in full_log:
        return ErrorType.ASSERTION_FAIL.value, _extract_signature(full_log, "AssertionError")
    
    return ErrorType.OTHER_RUNTIME.value, "unknown_runtime_error"

def _extract_signature(log: str, error_name: str) -> str:
    """
    Extracts a signature for the error. 
    Ideally: ErrorType + Top Frame (File:Line) + Key Entity
    """
    # Simple heuristic to extract the last relevant line triggering the error
    lines = log.splitlines()
    signature = error_name
    
    # regex for traceback file line
    # File "/path/to/file.py", line 10, in <module>
    tb_pattern = re.compile(r'File "([^"]+)", line (\d+), in (.+)')
    
    last_file = ""
    last_line = ""
    last_scope = ""

    for line in lines:
        match = tb_pattern.search(line)
        if match:
            last_file = match.group(1).split('/')[-1] # basename
            last_line = match.group(2)
            last_scope = match.group(3)
        
        # If the line contains the error name, we attach the last seen traceback info
        if error_name in line:
            # Clean up the line to remove the error name itself if needed, or keep it
            # e.g. "NameError: name 'foo' is not defined"
            # We want to capture 'foo'
            
            # If we found a traceback frame just before or recently
            if last_file:
                return f"{error_name}@{last_file}:{last_line} ({line.strip()})"
            else:
                return f"{error_name} ({line.strip()})"
                
    return signature
