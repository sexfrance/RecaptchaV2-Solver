import asyncio
from typing import Optional, Dict
from logmagix import Logger, Loader
from sync_solver import ReCaptchaSolver
from async_solver import AsyncReCaptchaSolver
from api_solver import app as api_app

class ReCaptchaTester:
    def __init__(self):
        self.log = Logger()
        self.loader = Loader(desc="Processing...", timeout=0.05)

    def _get_user_input(self) -> tuple[str, str, Dict, str]:
        """Get user input for solver configuration"""
        self.log.info("Select solver mode:")
        self.log.info("1. Sync Solver")
        self.log.info("2. Async Solver")
        self.log.info("3. API Server")
        
        mode = self.log.question("Enter mode (1-3): ")
        while mode not in ['1', '2', '3']:
            self.log.warning("Invalid mode. Please enter 1-3.")
            mode = self.log.question("Enter mode (1-3): ")

        if mode == '3':
            return 'api', '', None, ''

        url = self.log.question("URL (press enter for default 'https://yopmail.com/wm'): ").strip()
        url = url or "https://yopmail.com/wm"

        site_key = self.log.question("Site Key (press enter for default '6LcG5v8SAAAAAOdAn2iqMEQTdVyX8t0w9T3cpdN2'): ").strip()
        site_key = site_key or "6LcG5v8SAAAAAOdAn2iqMEQTdVyX8t0w9T3cpdN2"

        proxy = None
        use_proxy = self.log.question("Use proxy? (y/n): ").lower().strip() == 'y'
        if use_proxy:
            proxy = {
                "server": self.log.question("Proxy server (e.g., http://proxy:port): ")
            }
            
            username = self.log.question("Proxy username (optional, press enter to skip): ").strip()
            if username:
                proxy["username"] = username
                password = self.log.question("Proxy password: ").strip()
                if password:
                    proxy["password"] = password

        return {
            '1': 'sync',
            '2': 'async',
            '3': 'api'
        }[mode], url, proxy, site_key

    def run_sync_single(self, url: str, site_key: str, proxy: Optional[Dict] = None) -> str:
        """Run single synchronous solver"""
        try:
            solver = ReCaptchaSolver()
            return solver.solve_recaptcha(
                url=url,
                site_key=site_key,
                proxy=proxy,
                debug=True
            )
        except Exception as e:
            self.log.failure(f"Sync solver failed: {e}")
            return None


    async def run_async_single(self, url: str, site_key: str, proxy: Optional[Dict] = None) -> str:
        """Run single asynchronous solver"""
        try:
            return await AsyncReCaptchaSolver.solve_recaptcha(
                url=url,
                site_key=site_key,
                proxy=proxy,
                debug=True
            )
        except Exception as e:
            self.log.failure(f"Async solver failed: {e}")
            return None

    async def run_api_server(self):
        """Run the API server"""
        self.log.info("Starting API server on http://localhost:5000")
        self.log.info("Available endpoints:")
        self.log.info("  POST /solve - Solve single reCAPTCHA")
        self.log.info("  GET /health - Health check")
        
        try:
            await api_app.run_task(
                host="0.0.0.0",
                port=5000,
                debug=True
            )
        except Exception as e:
            self.log.failure(f"API server failed: {e}")

    async def main(self):
        """Main execution flow"""
        self.log.message("reCAPTCHA", "Welcome to reCAPTCHA Solver Tester")
        
        try:
            mode, url, proxy, site_key = self._get_user_input()

            if mode == 'api':
                await self.run_api_server()
                return

            token = None
            if mode == 'sync':
                token = self.run_sync_single(url, site_key, proxy)
            else:
                token = await self.run_async_single(url, site_key, proxy)

            if token:
                self.log.success(f"Token: {token[:50]}...")
            else:
                self.log.failure("Failed to get token")

        except KeyboardInterrupt:
            self.log.warning("\nOperation cancelled by user")
        except Exception as e:
            self.log.failure(f"An error occurred: {str(e)}")
        finally:
            self.log.message("reCAPTCHA", "Testing completed")

if __name__ == "__main__":
    tester = ReCaptchaTester()
    asyncio.run(tester.main())