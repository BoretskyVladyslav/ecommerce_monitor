"""
Captcha Solver Service
Інтеграція з 2Captcha та CapMonster Cloud для автоматичного вирішення капчі.
Підтримує різні типи: Slider, GeeTest, FunCaptcha, Grid, Click Points, Rotate.
"""
import asyncio
import aiohttp
import base64
import json
import time
from pathlib import Path
from typing import Optional, Dict, Any, List
from config.logger import setup_logger

logger = setup_logger("CaptchaSolver")


class SolverError(Exception):
    """Базова помилка solver"""
    pass


class SolverTimeoutError(SolverError):
    """Timeout при вирішенні капчі"""
    pass


class SolverAPIError(SolverError):
    """Помилка API (неправильний ключ, недостатньо коштів тощо)"""
    pass


class CaptchaSolution:
    """Рішення капчі від сервісу"""
    def __init__(
        self,
        solved: bool = False,
        solution_type: str = "",
        data: Any = None,
        cost: float = 0.0,
        solve_time: float = 0.0,
        service: str = ""
    ):
        self.solved = solved
        self.solution_type = solution_type  # coordinates, token, angle, text
        self.data = data  # Actual solution data
        self.cost = cost  # Cost in USD
        self.solve_time = solve_time  # Time taken to solve
        self.service = service  # Which service solved it
    
    def to_dict(self) -> Dict:
        """Конвертує в словник"""
        return {
            "solved": self.solved,
            "solution_type": self.solution_type,
            "data": self.data,
            "cost": self.cost,
            "solve_time": self.solve_time,
            "service": self.service
        }


class CaptchaSolver:
    """
    Універсальний сервіс для вирішення капчі.
    Підтримує 2Captcha та CapMonster Cloud APIs.
    """
    
    CONFIG_FILE = Path("config/captcha_config.json")
    
    def __init__(self, config_path: Optional[Path] = None):
        """
        Ініціалізація solver.
        
        Args:
            config_path: Шлях до конфігураційного файлу
        """
        self.config_path = config_path or self.CONFIG_FILE
        self.config = self._load_config()
        self.session = None
        
        # Вибираємо активний сервіс
        self.active_service = self.config.get("service", "capmonster").lower()
        
        if not self.config.get("enabled", False):
            logger.warning("⚠️ CaptchaSolver is DISABLED in config")
        else:
            logger.info(f"✅ CaptchaSolver initialized. Active service: {self.active_service}")
    
    def _load_config(self) -> Dict:
        """Завантажує конфігурацію з файлу"""
        try:
            if not self.config_path.exists():
                logger.warning(f"⚠️ Config not found: {self.config_path}")
                logger.info("Creating default config...")
                self._create_default_config()
            
            with open(self.config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"❌ Failed to load config: {e}")
            return {"enabled": False}
    
    def _create_default_config(self):
        """Створює конфігурацію за замовчуванням"""
        default_config = {
            "service": "capmonster",
            "enabled": False,
            "max_retries": 3,
            "fallback_to_manual": True,
            "2captcha": {
                "api_key": "YOUR_2CAPTCHA_API_KEY_HERE",
                "api_url": "https://2captcha.com",
                "timeout_seconds": 120,
                "poll_interval_seconds": 5
            },
            "capmonster": {
                "api_key": "YOUR_CAPMONSTER_API_KEY_HERE",
                "api_url": "https://api.capmonster.cloud",
                "timeout_seconds": 120,
                "poll_interval_seconds": 3
            }
        }
        
        try:
            self.config_path.parent.mkdir(exist_ok=True, parents=True)
            with open(self.config_path, 'w') as f:
                json.dump(default_config, f, indent=2)
            logger.info(f"✅ Created default config: {self.config_path}")
        except Exception as e:
            logger.error(f"❌ Failed to create config: {e}")
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Отримує або створює aiohttp session"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def close(self):
        """Закриває HTTP session"""
        if self.session and not self.session.closed:
            await self.session.close()
    
    # ==================== 2Captcha API ====================
    
    async def _solve_2captcha(
        self,
        captcha_type: str,
        image_base64: Optional[str] = None,
        additional_params: Optional[Dict] = None
    ) -> CaptchaSolution:
        """
        Вирішує капчу через 2Captcha API.
        
        Args:
            captcha_type: Тип капчі (slider, geetest, recaptcha, etc.)
            image_base64: Base64 зображення капчі
            additional_params: Додаткові параметри (site_key, page_url, etc.)
        """
        start_time = time.time()
        config = self.config.get("2captcha", {})
        api_key = config.get("api_key", "")
        api_url = config.get("api_url", "https://2captcha.com")
        
        if not api_key or "YOUR_" in api_key:
            raise SolverAPIError("2Captcha API key not configured")
        
        session = await self._get_session()
        
        try:
            # 1. Submit captcha
            logger.info(f"📤 Submitting to 2Captcha: {captcha_type}")
            
            submit_data = {
                "key": api_key,
                "json": 1,
            }
            
            # Різні параметри для різних типів
            if captcha_type in ["slider", "geetest"]:
                submit_data["method"] = "geetest"
                if additional_params:
                    submit_data.update(additional_params)
            
            elif captcha_type == "recaptcha_v2":
                submit_data["method"] = "userrecaptcha"
                submit_data["googlekey"] = additional_params.get("site_key", "")
                submit_data["pageurl"] = additional_params.get("page_url", "")
            
            elif captcha_type == "funcaptcha":
                submit_data["method"] = "funcaptcha"
                submit_data["publickey"] = additional_params.get("public_key", "")
                submit_data["pageurl"] = additional_params.get("page_url", "")
            
            elif image_base64:
                # Image-based captcha (coordinates, text)
                submit_data["method"] = "base64"
                submit_data["body"] = image_base64
                
                if captcha_type == "click_points":
                    submit_data["coordinatescaptcha"] = 1
                    submit_data["textinstructions"] = additional_params.get("instructions", "")
                
                elif captcha_type == "rotate":
                    submit_data["rotate"] = 1
            
            async with session.post(f"{api_url}/in.php", data=submit_data) as resp:
                result = await resp.json()
                
                if result.get("status") != 1:
                    raise SolverAPIError(f"2Captcha submit error: {result.get('request')}")
                
                task_id = result.get("request")
                logger.info(f"✅ Task submitted: {task_id}")
            
            # 2. Poll for result
            timeout = config.get("timeout_seconds", 120)
            poll_interval = config.get("poll_interval_seconds", 5)
            elapsed = 0
            
            while elapsed < timeout:
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval
                
                async with session.get(
                    f"{api_url}/res.php",
                    params={"key": api_key, "action": "get", "id": task_id, "json": 1}
                ) as resp:
                    result = await resp.json()
                    
                    if result.get("status") == 1:
                        # Solved!
                        solve_time = time.time() - start_time
                        solution_data = result.get("request")
                        
                        logger.info(f"✅ 2Captcha solved in {solve_time:.1f}s")
                        
                        return CaptchaSolution(
                            solved=True,
                            solution_type=self._get_solution_type(captcha_type),
                            data=self._parse_2captcha_solution(solution_data, captcha_type),
                            cost=0.003,  # Approximate cost
                            solve_time=solve_time,
                            service="2captcha"
                        )
                    
                    elif result.get("request") == "CAPCHA_NOT_READY":
                        logger.debug(f"⏳ Waiting for solution... ({elapsed}s)")
                        continue
                    
                    else:
                        raise SolverAPIError(f"2Captcha error: {result.get('request')}")
            
            raise SolverTimeoutError(f"2Captcha timeout after {timeout}s")
            
        except Exception as e:
            logger.error(f"❌ 2Captcha error: {e}")
            raise
    
    def _parse_2captcha_solution(self, solution: str, captcha_type: str) -> Any:
        """Парсить рішення від 2Captcha"""
        if captcha_type == "click_points":
            # Format could be "x1:y1;x2:y2" OR a list of objects/strings
            points = []
            
            # Handle list input (if 2Captcha returns parsed JSON)
            if isinstance(solution, list):
                for item in solution:
                    if isinstance(item, dict) and 'x' in item and 'y' in item:
                         points.append({"x": int(item['x']), "y": int(item['y'])})
                    elif isinstance(item, str) and ':' in item:
                         x, y = item.split(':')
                         points.append({"x": int(x), "y": int(y)})
                return points

            # Handle string input "x:y;x:y"
            if isinstance(solution, str):
                for coord in solution.split(";"):
                    if ':' in coord:
                        x, y = coord.split(":")
                        points.append({"x": int(x), "y": int(y)})
            return points
        
        elif captcha_type == "rotate":
            # Format: "angle:40"
            return int(solution.split(":")[-1])
        
        else:
            # Token or plain text
            return solution
    
    # ==================== CapMonster Cloud API ====================
    
    async def _solve_capmonster(
        self,
        captcha_type: str,
        image_base64: Optional[str] = None,
        additional_params: Optional[Dict] = None
    ) -> CaptchaSolution:
        """
        Вирішує капчу через CapMonster Cloud API.
        
        Args:
            captcha_type: Тип капчі
            image_base64: Base64 зображення
            additional_params: Додаткові параметри
        """
        start_time = time.time()
        config = self.config.get("capmonster", {})
        api_key = config.get("api_key", "")
        api_url = config.get("api_url", "https://api.capmonster.cloud")
        
        if not api_key or "YOUR_" in api_key:
            raise SolverAPIError("CapMonster API key not configured")
        
        session = await self._get_session()
        
        try:
            # 1. Create task
            logger.info(f"📤 Submitting to CapMonster: {captcha_type}")
            
            task_data = self._build_capmonster_task(
                captcha_type, image_base64, additional_params
            )
            
            create_payload = {
                "clientKey": api_key,
                "task": task_data
            }
            
            async with session.post(
                f"{api_url}/createTask",
                json=create_payload
            ) as resp:
                result = await resp.json()
                
                if result.get("errorId", 0) != 0:
                    raise SolverAPIError(f"CapMonster error: {result.get('errorDescription')}")
                
                task_id = result.get("taskId")
                logger.info(f"✅ Task created: {task_id}")
            
            # 2. Poll for result
            timeout = config.get("timeout_seconds", 120)
            poll_interval = config.get("poll_interval_seconds", 3)
            elapsed = 0
            
            while elapsed < timeout:
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval
                
                async with session.post(
                    f"{api_url}/getTaskResult",
                    json={"clientKey": api_key, "taskId": task_id}
                ) as resp:
                    result = await resp.json()
                    
                    if result.get("errorId", 0) != 0:
                        raise SolverAPIError(f"CapMonster error: {result.get('errorDescription')}")
                    
                    status = result.get("status")
                    
                    if status == "ready":
                        # Solved!
                        solve_time = time.time() - start_time
                        solution_data = result.get("solution", {})
                        
                        logger.info(f"✅ CapMonster solved in {solve_time:.1f}s")
                        
                        return CaptchaSolution(
                            solved=True,
                            solution_type=self._get_solution_type(captcha_type),
                            data=self._parse_capmonster_solution(solution_data, captcha_type),
                            cost=self._get_capmonster_cost(captcha_type),
                            solve_time=solve_time,
                            service="capmonster"
                        )
                    
                    elif status == "processing":
                        logger.debug(f"⏳ Waiting for solution... ({elapsed}s)")
                        continue
                    
                    else:
                        raise SolverAPIError(f"CapMonster unknown status: {status}")
            
            raise SolverTimeoutError(f"CapMonster timeout after {timeout}s")
            
        except Exception as e:
            logger.error(f"❌ CapMonster error: {e}")
            raise
    
    def _build_capmonster_task(
        self,
        captcha_type: str,
        image_base64: Optional[str],
        params: Optional[Dict]
    ) -> Dict:
        """Будує task payload для CapMonster"""
        params = params or {}
        
        if captcha_type == "slider":
            return {
                "type": "ImageToCoordinatesTask",
                "body": image_base64,
                "comment": "Click on the slider"
            }
        
        elif captcha_type == "geetest":
            return {
                "type": "GeeTestTask",
                "websiteURL": params.get("page_url", ""),
                "gt": params.get("gt", ""),
                "challenge": params.get("challenge", "")
            }
        
        elif captcha_type == "funcaptcha":
            return {
                "type": "FunCaptchaTask",
                "websiteURL": params.get("page_url", ""),
                "websitePublicKey": params.get("public_key", "")
            }
        
        elif captcha_type == "recaptcha_v2":
            return {
                "type": "RecaptchaV2Task",
                "websiteURL": params.get("page_url", ""),
                "websiteKey": params.get("site_key", "")
            }
        
        elif captcha_type == "click_points":
            return {
                "type": "ImageToCoordinatesTask",
                "body": image_base64,
                "comment": params.get("instructions", "Click in sequence")
            }
        
        elif captcha_type == "rotate":
            return {
                "type": "RotateTask",
                "body": image_base64
            }
        
        else:
            # Generic image task
            return {
                "type": "ImageToTextTask",
                "body": image_base64
            }
    
    def _parse_capmonster_solution(self, solution: Dict, captcha_type: str) -> Any:
        """Парсить рішення від CapMonster"""
        if captcha_type in ["slider", "click_points"]:
            # Coordinates
            coordinates = solution.get("coordinates", [])
            return [{"x": c[0], "y": c[1]} for c in coordinates]
        
        elif captcha_type == "rotate":
            return solution.get("rotate", 0)
        
        elif captcha_type == "geetest":
            return {
                "challenge": solution.get("challenge"),
                "validate": solution.get("validate"),
                "seccode": solution.get("seccode")
            }
        
        elif captcha_type in ["recaptcha_v2", "funcaptcha"]:
            return solution.get("gRecaptchaResponse") or solution.get("token")
        
        else:
            return solution.get("text", "")
    
    def _get_capmonster_cost(self, captcha_type: str) -> float:
        """Приблизна вартість вирішення"""
        costs = {
            "slider": 0.0008,
            "geetest": 0.002,
            "funcaptcha": 0.002,
            "recaptcha_v2": 0.001,
            "click_points": 0.0008,
            "rotate": 0.0008
        }
        return costs.get(captcha_type, 0.001)
    
    def _get_solution_type(self, captcha_type: str) -> str:
        """Визначає тип рішення"""
        if captcha_type in ["slider", "click_points"]:
            return "coordinates"
        elif captcha_type == "rotate":
            return "angle"
        elif captcha_type in ["recaptcha_v2", "funcaptcha", "geetest"]:
            return "token"
        else:
            return "text"
    
    # ==================== Public API ====================
    
    async def solve(
        self,
        captcha_type: str,
        image_path: Optional[str] = None,
        image_base64: Optional[str] = None,
        additional_params: Optional[Dict] = None
    ) -> CaptchaSolution:
        """
        Головний метод для вирішення капчі.
        
        Args:
            captcha_type: Тип капчі (slider, geetest, recaptcha_v2, etc.)
            image_path: Шлях до зображення капчі
            image_base64: Або base64 зображення
            additional_params: Додаткові параметри (залежить від типу)
        
        Returns:
            CaptchaSolution з результатом
        """
        if not self.config.get("enabled", False):
            logger.warning("⚠️ CaptchaSolver is disabled")
            return CaptchaSolution(solved=False)
        
        # Конвертуємо image_path в base64 якщо потрібно
        if image_path and not image_base64:
            try:
                with open(image_path, 'rb') as f:
                    image_base64 = base64.b64encode(f.read()).decode()
            except Exception as e:
                logger.error(f"❌ Failed to read image: {e}")
                return CaptchaSolution(solved=False)
        
        # Вибираємо сервіс
        max_retries = self.config.get("max_retries", 3)
        
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"🔄 Solve attempt {attempt}/{max_retries}")
                
                if self.active_service == "capmonster":
                    solution = await self._solve_capmonster(
                        captcha_type, image_base64, additional_params
                    )
                elif self.active_service == "2captcha":
                    solution = await self._solve_2captcha(
                        captcha_type, image_base64, additional_params
                    )
                else:
                    raise SolverError(f"Unknown service: {self.active_service}")
                
                if solution.solved:
                    logger.info(f"✅ Captcha solved successfully!")
                    logger.info(f"   Service: {solution.service}")
                    logger.info(f"   Time: {solution.solve_time:.1f}s")
                    logger.info(f"   Cost: ${solution.cost:.4f}")
                    return solution
                
            except SolverTimeoutError as e:
                logger.warning(f"⏳ Timeout on attempt {attempt}: {e}")
                if attempt == max_retries:
                    logger.error("❌ Max retries reached (timeout)")
                    return CaptchaSolution(solved=False)
            
            except SolverAPIError as e:
                logger.error(f"❌ API error: {e}")
                return CaptchaSolution(solved=False)
            
            except Exception as e:
                logger.error(f"❌ Unexpected error on attempt {attempt}: {e}")
                if attempt == max_retries:
                    return CaptchaSolution(solved=False)
        
        return CaptchaSolution(solved=False)
    
    async def get_balance(self) -> Optional[float]:
        """Отримує баланс активного сервісу"""
        try:
            session = await self._get_session()
            
            if self.active_service == "capmonster":
                config = self.config.get("capmonster", {})
                api_key = config.get("api_key", "")
                api_url = config.get("api_url")
                
                async with session.post(
                    f"{api_url}/getBalance",
                    json={"clientKey": api_key}
                ) as resp:
                    result = await resp.json()
                    balance = result.get("balance", 0)
                    logger.info(f"💰 CapMonster balance: ${balance:.2f}")
                    return balance
            
            elif self.active_service == "2captcha":
                config = self.config.get("2captcha", {})
                api_key = config.get("api_key", "")
                api_url = config.get("api_url")
                
                async with session.get(
                    f"{api_url}/res.php",
                    params={"key": api_key, "action": "getbalance", "json": 1}
                ) as resp:
                    result = await resp.json()
                    balance = float(result.get("request", 0))
                    logger.info(f"💰 2Captcha balance: ${balance:.2f}")
                    return balance
        
        except Exception as e:
            logger.error(f"❌ Failed to get balance: {e}")
            return None


# Глобальний інстанс
captcha_solver = CaptchaSolver()
