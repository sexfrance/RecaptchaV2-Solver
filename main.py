import asyncio
from typing import Optional, Dict, List, Tuple
from logmagix import Logger, Loader
from sync_solver import ReCaptchaSolver, CaptchaSolverPool
from async_solver import AsyncReCaptchaSolver, AsyncCaptchaSolverPool
from api_solver import app as api_app



class ReCaptchaTester:
    def __init__(self):
        self.log = Logger()
        self.loader = Loader(desc="Processing...", timeout=0.05)

    def _get_user_input(self) -> tuple[str, str, Dict, str]:
        """Get user input for solver configuration"""
        self.log.info("Select solver mode:")
        self.log.info("1. Sync Single Solver")
        self.log.info("2. Sync Multiple Solver")
        self.log.info("3. Async Single Solver")
        self.log.info("4. Async Multiple Solver")
        self.log.info("5. API Server")
        
        mode = self.log.question("Enter mode (1-5): ")
        while mode not in ['1', '2', '3', '4', '5']:
            self.log.warning("Invalid mode. Please enter 1-5.")
            mode = self.log.question("Enter mode (1-5): ")

        if mode == '5':
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
            
            # Make username and password optional
            username = self.log.question("Proxy username (optional, press enter to skip): ").strip()
            if username:
                proxy["username"] = username
                password = self.log.question("Proxy password: ").strip()
                if password:
                    proxy["password"] = password

        return {
            '1': 'sync_single',
            '2': 'sync_multiple',
            '3': 'async_single',
            '4': 'async_multiple',
            '5': 'api'
        }[mode], url, proxy, site_key

    def run_sync_single(self, url: str, site_key: str, proxy: Optional[Dict] = None) -> str:
        """Run single synchronous solver"""
        try:
            return ReCaptchaSolver.solve_recaptcha(
                url=url,
                site_key=site_key,
                proxy=proxy,
                debug=True
            )
        except Exception as e:
            self.log.failure(f"Sync solver failed: {e}")
            return None

    def run_sync_multiple(self, tasks: List[Dict]) -> List[Tuple[Dict, Optional[str], Optional[str]]]:
        """Run multiple synchronous solvers"""
        try:
            solver_pool = CaptchaSolverPool(max_workers=3)
            return solver_pool.solve_multiple(tasks)
        except Exception as e:
            self.log.failure(f"Sync multiple solver failed: {e}")
            return []

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

    async def run_async_multiple(self, tasks: List[Dict]) -> List[Tuple[Dict, Optional[str], Optional[str]]]:
        """Run multiple asynchronous solvers"""
        try:
            solver_pool = AsyncCaptchaSolverPool(max_concurrent=3)
            return await solver_pool.solve_multiple(tasks)
        except Exception as e:
            self.log.failure(f"Async multiple solver failed: {e}")
            return []

    async def run_api_server(self):
        """Run the API server"""
        self.log.info("Starting API server on http://localhost:8080")
        self.log.info("Available endpoints:")
        self.log.info("  POST /solve - Solve single reCAPTCHA")
        self.log.info("  POST /solve_batch - Solve multiple reCAPTCHAs")
        self.log.info("  GET /health - Health check")
        
        try:
            import hypercorn.asyncio
            config = hypercorn.Config()
            config.bind = ["localhost:8080"]
            await hypercorn.asyncio.serve(api_app, config)
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

            if mode in ['sync_multiple', 'async_multiple']:
                num_tasks = int(self.log.question("Number of tasks to run (1-10): "))
                num_tasks = max(1, min(10, num_tasks))
                
                tasks = [
                    {
                        'url': url,
                        'site_key': site_key,
                        'proxy': proxy,
                        'debug': True
                    }
                    for _ in range(num_tasks)
                ]

                if mode == 'sync_multiple':
                    results = self.run_sync_multiple(tasks)
                else:
                    results = await self.run_async_multiple(tasks)

                for i, (task, token, error) in enumerate(results, 1):
                    if token:
                        self.log.success(f"Task {i}: Success - Token: {token[:50]}...")
                    else:
                        self.log.failure(f"Task {i}: Failed - Error: {error}")

            else:  # Single solver modes
                token = None
                if mode == 'sync_single':
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