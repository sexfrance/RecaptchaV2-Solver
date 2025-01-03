from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple
import io
import time
import requests
import speech_recognition as sr
from pydub import AudioSegment
from patchright.sync_api import sync_playwright, Page, TimeoutError
from logmagix import Logger, Loader
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading


@dataclass
class BrowserConfig:
    """Configuration for browser launch arguments"""
    CHROME_ARGS: List[str] = field(default_factory=lambda: [
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-background-networking",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        "--disable-features=IsolateOrigins,site-per-process",
        "--disable-web-security",
        "--disable-images",
    ])
    CONTEXT_OPTIONS: Dict = field(default_factory=lambda: {
        "locale": "en-US",
        "java_script_enabled": True,
        "bypass_csp": True,
        "device_scale_factor": 1,
        "is_mobile": False,
        "offline": False,
        "ignore_https_errors": True,
        "service_workers": "block"
    })

class AudioProcessor:
    """Handles audio processing and speech recognition"""
    def __init__(self, debug: bool = False):
        self.recognizer = sr.Recognizer()
        self.debug = debug
        self.log = Logger()

    def process_audio(self, audio_url: str) -> str:
        """Download and process audio file"""
        response = self._download_audio(audio_url)
        audio_bytes = self._convert_to_wav(response.content)
        return self._convert_audio_to_text(audio_bytes)

    def _download_audio(self, audio_url: str) -> requests.Response:
        """Download audio file from URL"""
        response = requests.get(audio_url, timeout=5)
        if response.status_code != 200:
            raise Exception(f"Failed to download audio file. Status code: {response.status_code}")
        return response

    def _convert_to_wav(self, audio_content: bytes) -> io.BytesIO:
        """Convert MP3 audio to WAV format"""
        audio_bytes = io.BytesIO(audio_content)
        audio = AudioSegment.from_mp3(audio_bytes)
        audio = audio.set_frame_rate(16000).set_channels(1)
        wav_bytes = io.BytesIO()
        audio.export(wav_bytes, format="wav", parameters=["-q:a", "0"])
        wav_bytes.seek(0)
        return wav_bytes

    def _convert_audio_to_text(self, wav_bytes: io.BytesIO) -> str:
        """Convert audio to text using speech recognition"""
        with sr.AudioFile(wav_bytes) as source:
            audio = self.recognizer.record(source)
            try:
                text = str(self.recognizer.recognize_google(audio))
                if self.debug:
                    self.log.debug(f"Raw recognized text: {text}")
                cleaned_text = ''.join(c.lower() for c in text if c.isalnum() or c.isspace())
                if self.debug:
                    self.log.debug(f"Cleaned text: {cleaned_text}")
                if not cleaned_text:
                    try:
                        Loader.stop()
                    except:
                        pass
                    raise sr.UnknownValueError("Empty audio response")
                return cleaned_text.strip()
            except sr.UnknownValueError:
                try:
                    Loader.stop()
                except:
                    pass
                raise Exception("Could not understand audio")
            except sr.RequestError:
                try:
                    Loader.stop()
                except:
                    pass
                raise Exception("Could not request results from speech recognition service")
            except Exception as e:
                try:
                    Loader.stop()
                except:
                    pass
                if self.debug:
                    self.log.debug(f"Error type: {type(e)}")
                self.log.failure(f"Error message: {str(e)}")
                raise Exception(f"Unexpected error in audio conversion: {str(e)}")

class ReCaptchaSolver:
    """Main class for solving reCAPTCHA challenges"""
    HTML_TEMPLATE =  """
<!DOCTYPE html>
<html>
    <head>
        <script src="https://www.google.com/recaptcha/api.js" async
            defer></script>
    </head>
    <body>
        <div
            class="g-recaptcha"
            data-sitekey="{sitekey}"></div>
    </body>
</html>
"""

    def __init__(self, page: Page, debug: bool = False):
        self.page = page
        self.debug = debug
        self.log = Logger()
        has_proxy = bool(getattr(page, 'proxy', None))
        self.page.set_default_timeout(20000 if has_proxy else 8000)
        self.audio_processor = AudioProcessor(debug)

    def solve_recaptcha(self, url: str, proxy: Optional[Dict] = None, debug: bool = False, site_key: Optional[str] = None, headless: bool = True, wait: int = None, check_score: bool = False) -> str:
        """Solve reCAPTCHA from URL or using a site key"""
        if check_score and not site_key:
            raise ValueError("Score checking requires a site key to be provided")
        
        loader = Loader(desc="Solving reCAPTCHA...", timeout=0.05)
        loader.start()
        start_time = time.time()

        try:
            browser_config = BrowserConfig()
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=headless, args=browser_config.CHROME_ARGS)
                context_options = browser_config.CONTEXT_OPTIONS.copy()
                if proxy:
                    context_options["proxy"] = proxy
                context = browser.new_context(**context_options)
                page = context.new_page()

                try:
                    page.goto(url, wait_until="commit")
                    if site_key:
                        page.set_content(self.HTML_TEMPLATE.format(sitekey=site_key))
                    
                    token = self._solve(page)
                    end_time = time.time()
                    loader.stop()

                    if debug and check_score:
                        Logger().debug(f"Checking score...")

                    if check_score:
                        try:
                            response = requests.post('https://2captcha.com/api/v1/captcha-demo/recaptcha-enterprise/verify', 
                                json={
                                    'siteKey': site_key,
                                    'token': token,
                                })
                            result = response.json()
                            if debug:
                                Logger().debug(f"Got response for score: {result}")
                            score = result.get("riskAnalysis", {}).get("score")
                        except Exception as e:
                            Logger().failure(f"Failed to check score: {e}")
                            score = "Unknown"
                    
                    if debug and check_score:
                        Logger().debug(f"Got score: {score}")

                    Logger().message(
                        "reCAPTCHA",
                        f"Successfully solved captcha {token[:60]}..." if not check_score else f"Successfully solved captcha {token[:60]}... and score is {score}",
                        start=start_time,
                        end=end_time
                    )
                    return token

                except Exception as e:
                    loader.stop()
                    if "rate limit" in str(e).lower():
                        if proxy:
                            raise Exception("Rate limit reached, consider using or changing your proxy. Please use a different proxy.")
                        else:
                            raise Exception("Rate limit reached, consider using or changing your proxy.")
                    raise e
                finally:
                    if wait:
                        time.sleep(wait)
                    context.close()
                    browser.close()
        except Exception as e:
            loader.stop()
            raise e

    def _solve(self, page: Page) -> str:
        """Internal method to solve the reCAPTCHA"""
        try:
            iframe = self._handle_initial_iframe()
            challenge_iframe = self._handle_challenge_iframe()
            if not challenge_iframe:
                return self._get_token()
            audio_url = self._get_audio_challenge(challenge_iframe)
            audio_text = self.audio_processor.process_audio(audio_url)
            self._submit_audio_solution(challenge_iframe, audio_text)
            return self._get_token()
        except Exception as e:
            try:
                Loader.stop()
            except:
                pass
            raise Exception(f"Failed to solve reCAPTCHA: {str(e)}")

    def _handle_initial_iframe(self) -> Optional[Page]:
        """Handle the initial reCAPTCHA iframe"""
        iframe = self.page.wait_for_selector(
            "iframe[src*='google.com/recaptcha/api2/anchor'], iframe[src*='google.com/recaptcha/enterprise/anchor']",
            strict=True
        )
        iframe = iframe.content_frame()
        checkbox = iframe.wait_for_selector("#recaptcha-anchor", state="visible", strict=True)
        checkbox.click()
        return iframe

    def _handle_challenge_iframe(self) -> Optional[Page]:
        """Handle the challenge iframe"""
        has_proxy = bool(getattr(self.page, 'proxy', None))
        challenge_iframe = self.page.wait_for_selector(
            "iframe[src*='google.com/recaptcha/api2/bframe'], iframe[src*='google.com/recaptcha/enterprise/bframe']",
            timeout=10000 if has_proxy else 3000,
            strict=True
        )
        return challenge_iframe.content_frame()

    def _get_audio_challenge(self, challenge_iframe: Page) -> str:
        """Get audio challenge URL"""
        has_proxy = bool(getattr(self.page, 'proxy', None))
        try:
            audio_button = challenge_iframe.wait_for_selector(
                "#recaptcha-audio-button",
                state="visible",
                timeout=5000 if has_proxy else 2000,
                strict=True
            )
            audio_button.click()
        except TimeoutError:
            try:
                Loader.stop()
            except:
                pass
            if self._check_rate_limit(challenge_iframe):
                if hasattr(self.page, 'proxy'):
                    raise Exception("Rate limit reached, consider using or changing your proxy. Please use a different proxy.")
                raise Exception("Rate limit reached, consider using or changing your proxy.")

        try:
            download_button = challenge_iframe.wait_for_selector(
                ".rc-audiochallenge-tdownload-link", 
                state="visible", 
                timeout=12000 if has_proxy else 5000
            )
            audio_url = download_button.get_attribute("href")
            if not audio_url:
                try:
                    Loader.stop()
                except:
                    pass
                raise Exception("Could not get audio URL")
            return audio_url
        except TimeoutError:
            try:
                Loader.stop()
            except:
                pass
            if self._check_rate_limit(challenge_iframe):
                if hasattr(self.page, 'proxy'):
                    raise Exception("Rate limit reached, consider using or changing your proxy. Please use a different proxy.")
                raise Exception("Rate limit reached, consider using or changing your proxy.")
            raise

    def _submit_audio_solution(self, challenge_iframe: Page, audio_text: str) -> None:
        """Submit the audio challenge solution"""
        response_input = challenge_iframe.wait_for_selector("#audio-response", state="visible")
        response_input.fill(audio_text)
        verify_button = challenge_iframe.wait_for_selector("#recaptcha-verify-button", state="visible")
        verify_button.click()

    def _check_rate_limit(self, frame: Page) -> bool:
        """Check if rate limit has been reached"""
        try:
            rate_limit_message = frame.locator(".rc-doscaptcha-header").text_content()
            return "Try again later" in rate_limit_message
        except:
            return False

    def _get_token(self) -> str:
        """Get the reCAPTCHA token using multiple methods"""
        token_methods = [
            self._get_response_token,
            self._get_bframe_token,
            self._get_frame_token,
            self._get_enterprise_token
        ]

        for method in token_methods:
            try:
                token = method()
                if token:
                    if self.debug:
                        self.log.debug(f"Found token using {method.__name__}: {token}")
                    return str(token)
            except Exception as e:
                if self.debug:
                    self.log.debug(f"Error in {method.__name__}: {str(e)}")

        raise Exception("Could not retrieve reCAPTCHA token")

    def _get_response_token(self) -> Optional[str]:
        """Get token from g-recaptcha-response"""
        return self.page.evaluate('''() => {
            const response = document.getElementById('g-recaptcha-response');
            return response ? response.value : null;
        }''')

    def _get_bframe_token(self) -> Optional[str]:
        """Get token from bframe"""
        return self.page.evaluate('''() => {
            for (const frame of window.frames) {
                try {
                    const token = frame.document.getElementById('recaptcha-token');
                    if (token) return token.value;
                } catch (e) {}
            }
            return null;
        }''')

    def _get_frame_token(self) -> Optional[str]:
        """Get token from frames"""
        for frame in self.page.frames:
            try:
                token = frame.evaluate('document.getElementById("recaptcha-token").value')
                if token:
                    return token
            except:
                continue
        return None

    def _get_enterprise_token(self) -> Optional[str]:
        """Get token from enterprise recaptcha"""
        return self.page.evaluate('''() => {
            const response = document.querySelector('[name="recaptcha-token"]');
            return response ? response.value : null;
        }''')

if __name__ == "__main__":
    try:
        token = ReCaptchaSolver.solve_recaptcha(
            "https://2captcha.com/demo/recaptcha-v2-enterprise", 
            headless=False, 
            debug=True, 
            check_score=True,
            site_key="6LfB5B8UAAAAAJgXZxP_d-9KzXaqFzYGpXzJ2sFP"
        ) 
        print(token)
    except Exception as e:
        Logger().failure(f"Failed to solve reCAPTCHA: {e}")