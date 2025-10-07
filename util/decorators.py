from functools import wraps
from playwright.sync_api import sync_playwright, BrowserContext, Browser
from typing import Callable, TypeVar, ParamSpec, cast, Any

# Define Type Variables for generics
P = ParamSpec('P')  # Captures the parameter specification (names and types)
R = TypeVar('R')    # Captures the return type of the decorated function

# --- Helper function for Playwright context management ---

def _execute_with_playwright_context(
    func: Callable[P, R], 
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    storage_state_file: str, 
    headless: bool, 
    slow_mo: int
) -> R:
    """
    Handles the setup/teardown of the Playwright context and executes the 
    wrapped function. The injected arguments are handled internally.
    """
    print("Starting Playwright context...")
    
    # We use 'Any' for the Playwright types here since we can't easily 
    # infer which args the user's function expects without introspection.
    # However, by using P and R on 'func', we maintain type safety for the rest.
    
    with sync_playwright() as p:
        browser: Browser = p.chromium.launch(headless=headless, slow_mo=slow_mo)
        try:
            # 1. Setup context
            context: BrowserContext = browser.new_context(storage_state=storage_state_file)
            
            # 2. Inject Playwright objects into keyword arguments
            # Note: This is the part that breaks strict type compatibility,
            # requiring careful handling or a slight relaxation of typing on the func call.
            final_kwargs = dict(kwargs)
            final_kwargs['playwright'] = p
            final_kwargs['browser'] = browser
            final_kwargs['context'] = context
            
            # 3. Execute the function. We must cast the result to R 
            # because the signature of 'func' (P -> R) doesn't explicitly 
            # include the injected kwargs in the P spec.
            result = func(*args, **final_kwargs)
            return result
            
        finally:
            print("Closing browser.")
            browser.close()

# --- Refactored Decorator Factory (Type-safe using P and R) ---

def playwright_browser_context(
    storage_state_file: str = "linkedin_state.json", 
    headless: bool = False, 
    slow_mo: int = 50
) -> Callable[[Callable[P, R]], Callable[P, R]]: 
    """
    A decorator factory that injects 'playwright', 'browser', and 'context'
    keyword arguments into the decorated function.
    
    Uses Callable[[Callable[P, R]], Callable[P, R]] to satisfy Pylance 
    by ensuring the decorator's returned function maintains the input's 
    type signature P -> R.
    """
    
    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R: 
            # Calls the helper function with all required parameters
            return _execute_with_playwright_context(
                func, 
                args, 
                kwargs, 
                storage_state_file, 
                headless, 
                slow_mo
            )
        
        # We cast the wrapper to Callable[P, R] to ensure the type checker 
        # believes the wrapper has the same signature as the original function.
        return cast(Callable[P, R], wrapper)
    
    return decorator

# --------------------------------------------------------------------------

## returns_exception_on_error Decorator (Fully Type-Safe)

def returns_exception_on_error(func: Callable[P, R]) -> Callable[P, R | Exception]: 
    """
    Decorator that executes the wrapped function and returns any Exception 
    that occurs as a value, rather than raising it.
    
    This is fully type-safe: the resulting function's return type is R | Exception.
    """
    
    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R | Exception:
        # P.args and P.kwargs ensure the wrapper's signature matches the original func.
        # R | Exception ensures type checkers know the function now returns a union.
        try:
            result: R = func(*args, **kwargs)
            return result
        except Exception as e:
            # Catch any exception and return the exception instance itself.
            return e
            
    return wrapper