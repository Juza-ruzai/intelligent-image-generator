import os
import base64 
import requests
from io import BytesIO
from PIL import Image
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

# --- 模型相关的导入 ---
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions

# --- 初始化和配置 ---
load_dotenv()

# Vercel部署需要将静态文件目录指向上一级的'static'文件夹
app = Flask(__name__, static_folder='../static', static_url_path='')
CORS(app)

# --- 根路由，用于服务前端HTML文件 ---
@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'index.html')

# --- 模型处理函数 ---
def _process_with_gemini(api_key, prompt, image_bytes):
    """使用Gemini模型处理图像（图生图）"""
    genai.configure(api_key=api_key)
    image = Image.open(BytesIO(image_bytes)) 
    model = genai.GenerativeModel('gemini-2.5-flash-image-preview')
    
    print("正在通过 Gemini SDK 发送请求...")
    response = model.generate_content(
        contents=[prompt, image],
        generation_config={"response_modalities": ['IMAGE']}
    )
    if hasattr(response, 'prompt_feedback') and response.prompt_feedback.block_reason:
        reason = response.prompt_feedback.block_reason.name
        raise ValueError(f"请求因安全原因被阻止: {reason}。")
    generated_part = response.candidates[0].content.parts[0]
    if not generated_part.inline_data:
        raise ValueError("API响应中未找到有效的图片数据。")
    return generated_part.inline_data.data

def _process_with_ark(api_key, prompt, image_bytes=None):
    """
    该函数统一了文生图 (text-to-image) 和图生图 (image-to-image) 的调用。
    """
    print("正在调用最新的火山方舟API (doubao-seedream-4.0)...")
    
    url = "https://ark.cn-beijing.volces.com/api/v3/images/generations"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    payload = {
        "model": "doubao-seedream-4-0-250828",
        "prompt": prompt,
        "size": "2K",
        "sequential_image_generation": "disabled",
        "stream": False,
        "response_format": "url",
        "watermark": False
    }

    if image_bytes:
        print("检测到图片输入，进入图生图模式。")
        try:
            image_format = Image.open(BytesIO(image_bytes)).format.lower()
        except Exception:
            image_format = "png"
        
        base64_encoded_image = base64.b64encode(image_bytes).decode('utf-8')
        image_data_uri = f"data:image/{image_format};base64,{base64_encoded_image}"
        payload["image"] = image_data_uri
    else:
         print("无图片输入，进入文生图模式。")

    response = requests.post(url, headers=headers, json=payload, timeout=120)
    response.raise_for_status()

    result = response.json()
    
    if "error" in result:
         raise ValueError(f"火山方舟API返回错误: {result['error']}")

    if not result.get("data") or not result["data"][0].get("url"):
        raise ValueError("火山方舟API未能返回有效的图片URL。")
        
    image_url = result["data"][0]["url"]
    print(f"成功获取图片URL，正在下载...")
    
    image_response = requests.get(image_url, timeout=60)
    image_response.raise_for_status()
    
    return image_response.content


# --- API路由 ---
@app.route('/api/generate', methods=['POST'])
def generate_image_proxy():
    """统一的API端点，根据前端请求分发任务"""
    try:
        model_choice = request.form.get('model')
        prompt = request.form.get('prompt')
        image_file = request.files.get('image')

        if not all([model_choice, prompt]):
            return jsonify({"error": "请求中缺少 'model' 或 'prompt'。"}), 400

        api_key = None
        if "gemini" in model_choice.lower():
            api_key = os.getenv("GOOGLE_API_KEY")
        elif "ark" in model_choice.lower():
            api_key = os.getenv("ARK_API_KEY")

        if not api_key:
            return jsonify({"error": f"未能找到 {model_choice} 对应的环境变量API密钥。"}), 400

        generated_bytes = None
        if model_choice == 'gemini_i2i':
            if not image_file: return jsonify({"error": "Gemini模型需要上传图片。"}), 400
            generated_bytes = _process_with_gemini(api_key, prompt, image_file.read())
        
        elif model_choice == 'ark_t2i':
            generated_bytes = _process_with_ark(api_key, prompt)

        elif model_choice == 'ark_i2i':
            if not image_file: return jsonify({"error": "Ark图生图模型需要上传图片。"}), 400
            generated_bytes = _process_with_ark(api_key, prompt, image_file.read())
        
        else:
            return jsonify({"error": f"未知的模型标识: {model_choice}"}), 400

        generated_base64 = base64.b64encode(generated_bytes).decode('utf-8')
        print("图片生成成功，正在返回给前端。")
        return jsonify({"imageData": generated_base64})

    except (google_exceptions.ResourceExhausted, google_exceptions.DeadlineExceeded) as e:
        print(f"Google API 错误: {e}")
        error_message = getattr(e, 'message', str(e))
        return jsonify({"error": f"Google API 错误: {error_message}"}), 500
    except requests.exceptions.RequestException as e:
        print(f"网络请求错误: {e}")
        return jsonify({"error": f"网络请求失败: {str(e)}"}), 500
    except Exception as e:
        print(f"服务器内部错误: {e}")
        return jsonify({"error": f"服务器内部错误: {str(e)}"}), 500

# Vercel不需要下面的主程序入口
# if __name__ == '__main__':
#     app.run(debug=True, port=5001)
