"""
Utility functions for authentication.
"""
from fastapi import Request
from user_agents import parse


def get_client_ip(request: Request) -> str:
    """
    Extract client IP from request, handling proxies.
    
    Checks headers in order:
    1. X-Forwarded-For (from reverse proxies/load balancers)
    2. X-Real-IP (from nginx)
    3. Direct client connection
    """
    # Check X-Forwarded-For header (can contain multiple IPs, first is client)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    
    # Check X-Real-IP header
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    
    # Direct connection
    if request.client:
        return request.client.host
    
    return "unknown"


def get_device_info(request: Request) -> str:
    """
    Extract readable device info (OS, Browser) combined with IP.
    Example: "Windows 10 / Chrome (192.168.1.10)"
    """
    ip = get_client_ip(request)
    ua_string = request.headers.get("User-Agent", "")
    
    if not ua_string:
        return ip
        
    try:
        user_agent = parse(ua_string)
        os_info = user_agent.os.family
        if user_agent.os.version_string:
            os_info += f" {user_agent.os.version_string}"
            
        browser_info = user_agent.browser.family
        # Optional: Add browser version if needed, but family is usually enough
        
        device_str = f"{os_info} / {browser_info} ({ip})"
        return device_str
    except Exception:
        # Fallback to just IP if parsing fails
        return ip
