from quart import Quart, request, jsonify
from async_solver import AsyncReCaptchaSolver
from logmagix import Logger
from typing import Dict, Optional
import json

app = Quart(__name__)
logger = Logger()

@app.route('/health', methods=['GET'])
async def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "service": "recaptcha-solver-api"})

@app.route('/solve', methods=['POST'])
async def solve_captcha():
    """
    Solve reCAPTCHA endpoint
    
    Expected JSON body:
    {
        "url": "string",
        "sitekey": "string" (optional),
        "proxy": {
            "server": "string",
            "username": "string",
            "password": "string"
        } (optional),
        "headless": boolean (optional, default true),
        "debug": boolean (optional, default false),
        "check_score": boolean (optional, default false)
    }
    """
    try:
        data = await request.get_json()
        
        if not data or 'url' not in data:
            return jsonify({
                "error": "Missing required parameter: url"
            }), 400

        url: str = data['url']
        site_key: Optional[str] = data.get('sitekey')
        proxy_config: Optional[Dict] = data.get('proxy')
        headless: bool = data.get('headless', True)
        debug: bool = data.get('debug', False)
        check_score: bool = data.get('check_score', False)

        # Configure proxy if provided
        proxy = None
        if proxy_config:
            proxy = {
                'server': proxy_config['server'],
                'username': proxy_config.get('username'),
                'password': proxy_config.get('password')
            }

        # Solve the captcha
        try:
            token = await AsyncReCaptchaSolver.solve_recaptcha(
                url=url,
                site_key=site_key,
                proxy=proxy,
                headless=headless,
                debug=debug,
                check_score=check_score
            )

            return jsonify({
                "success": True,
                "token": token
            })

        except Exception as e:
            logger.failure(f"Solver error: {str(e)}")
            return jsonify({
                "success": False,
                "error": str(e)
            }), 500

    except json.JSONDecodeError:
        return jsonify({
            "error": "Invalid JSON payload"
        }), 400
    
    except Exception as e:
        logger.failure(f"Server error: {str(e)}")
        return jsonify({
            "error": f"Server error: {str(e)}"
        }), 500

@app.errorhandler(404)
async def not_found(error):
    """Handle 404 errors"""
    return jsonify({
        "error": "Not found"
    }), 404

@app.errorhandler(405)
async def method_not_allowed(error):
    """Handle 405 errors"""
    return jsonify({
        "error": "Method not allowed"
    }), 405

@app.errorhandler(500)
async def server_error(error):
    """Handle 500 errors"""
    return jsonify({
        "error": "Internal server error"
    }), 500

if __name__ == '__main__':
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True
    )
