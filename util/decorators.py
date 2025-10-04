from functools import wraps
from playwright.sync_api import sync_playwright, BrowserContext, Browser
from typing import Callable, TypeVar, ParamSpec, Any, cast

# Define ParamSpec and TypeVar
P = ParamSpec('P') 
R = TypeVar('R') 

# Define a TypeVar for the function being decorated. This is the source of truth for Pylance.
F = TypeVar('F', bound=Callable[..., Any]) 

def playwright_browser_context(
    storage_state_file: str = "linkedin_state.json", 
    headless: bool = False, 
    slow_mo: int = 50
) -> Callable[[F], F]: 
    
    def decorator(func: F) -> F:
        
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs): 
            print("Starting Playwright context...")
            with sync_playwright() as p:
                browser: Browser = p.chromium.launch(headless=headless, slow_mo=slow_mo)
                try:
                    context: BrowserContext = browser.new_context(storage_state=storage_state_file)
                    
                    # Merge the injected keyword arguments
                    final_kwargs = dict(kwargs)
                    final_kwargs['playwright'] = p
                    final_kwargs['browser'] = browser
                    final_kwargs['context'] = context
                    
                    result = func(*args, **final_kwargs)
                    
                    return result
                    
                finally:
                    print("Closing browser.")
                    browser.close()
        
        # The cast on the return value of the decorator function is still necessary and correct
        return cast(F, wrapper)
    
    return decorator


def returns_exception_on_error(func: Callable[P, R]) -> Callable[P, R | Exception]: 
    """
    Decorator that executes the wrapped function and returns any Exception 
    that occurs as a value, rather than raising it.

    This is type-safe: the resulting function's return type is R | Exception.

    Args:
        func (Callable[P, R]): The function to be decorated.

    Returns:
        Callable[P, R | Exception]: A wrapper function that returns the result R 
                                    on success, or an Exception instance on failure.
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
