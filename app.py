import os
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from together import Together
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

client = Together(api_key=os.getenv("TOGETHER_API_KEY"))

def processar_gasto_com_ia(texto_usuario):
    system_prompt = """
    Você é um assistente financeiro que registra gastos.
    Analise a mensagem do usuário e extraia: 
    1. O item comprado.
    2. O valor (converta para número).
    3. A categoria (Alimentação, Transporte, Lazer, Contas, Outros).
    
    Retorne APENAS um JSON puro, sem crase, sem markdown. Exemplo:
    {"item": "pizza", "valor": 50.00, "categoria": "Alimentação"}
    
    Se não for um gasto, retorne: {"erro": "não identifiquei gasto"}
    """

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": texto_usuario}
    ]

    try:
        response = client.chat.completions.create(
            model="openai/gpt-oss-20b", 
            messages=messages,
            temperature=0.2, 
            max_tokens=500
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Erro na IA: {str(e)}"

@app.route("/webhook", methods=['POST'])
def bot():
    msg_usuario = request.values.get('Body', '')
    print(f"Mensagem recebida: {msg_usuario}")

    resultado_ia = processar_gasto_com_ia(msg_usuario)
    print(f"IA respondeu: {resultado_ia}")

    resp = MessagingResponse()
    msg = resp.message()
    
    msg.body(f"✅ Anotei:\n{resultado_ia}")

    return str(resp)

if __name__ == "__main__":
    app.run(port=5000, debug=True)