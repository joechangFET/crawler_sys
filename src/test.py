# 安装 CapSolver SDK
# pip install --upgrade capsolver

# 设置 CapSolver API 密钥
# export CAPSOLVER_API_KEY='YOUR_API_KEY'

import capsolver
capsolver.api_key = 'CAP-DC02DBB6D890DC40DDD2782C3AF2D752FB00E620C27BFA3FE5584FAE7130E5A3'

# 解决一个 reCAPTCHA v2 挑战
solution = capsolver.solve({
    "type": "ReCaptchaV2TaskProxyLess",
    "websiteURL": "https://www.google.com/recaptcha/api2/demo",
    "websiteKey": "6Le-wvkSAAAAAPBMRTvw0Q4Muexq9bi0DJwx_mJ-",
})