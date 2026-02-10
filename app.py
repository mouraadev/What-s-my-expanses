import os
import datetime
import pytz
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from together import Together
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

client = Together(api_key=os.getenv("TOGETHER_API_KEY"))

conversa_ativa = {}

def obter_contexto_temporal(user_id):
    """
    Define se é inicio de conversa ou continuação.
    """
    fuso_brasil = pytz.timezone('America/Sao_Paulo')
    agora = datetime.datetime.now(fuso_brasil)
    
    ultima_vez = conversa_ativa.get(user_id)
    conversa_ativa[user_id] = agora 

    hora = agora.hour
    if 5 <= hora < 12:
        saudacao_tempo = "Bom dia"
    elif 12 <= hora < 18:
        saudacao_tempo = "Boa tarde"
    else:
        saudacao_tempo = "Boa noite"

    if ultima_vez and (agora - ultima_vez).total_seconds() < 600:
        return {
            "saudacao": saudacao_tempo,
            "tipo": "CONTINUACAO", 
            "instrucao": "O usuário já está falando com você. NÃO dê Bom dia/Tarde de novo. Seja breve."
        }
    else:
        return {
            "saudacao": saudacao_tempo,
            "tipo": "INICIO", 
            "instrucao": f"Comece a frase com '{saudacao_tempo}'."
        }

def processar_mensagem(texto_usuario, user_id):
    ctx = obter_contexto_temporal(user_id)
    
    system_prompt = f"""
    Você é a F.R.I.D.A.Y., uma assistente financeira pessoal.
    
    SUA MISSÃO É CLASSIFICAR A MENSAGEM DO USUÁRIO EM DOIS TIPOS:

    ---
    CENÁRIO 1: O USUÁRIO APENAS CUMPRIMENTOU (Ex: "Oi", "Bom dia", "Tudo bem?", "Ola")
    ---
    AÇÃO: Apenas retribua o cumprimento educadamente e pergunte qual foi o gasto.
    REGRA CRÍTICA: NÃO invente gastos. NÃO diga "Anotei seus gastos".
    
    Exemplo de resposta (Cenário 1):
    "{ctx['saudacao']}! Tudo pronto por aqui. Qual gasto você quer registrar?"

    ---
    CENÁRIO 2: O USUÁRIO ENVIOU UM GASTO (Ex: "Gastei 20 no mercado", "Uber 15 reais", "Almoço 30")
    ---
    AÇÃO: Extraia os dados e confirme o registro.
    
    Exemplo de resposta (Cenário 2):
    "{ 'Entendido!' if ctx['tipo'] == 'CONTINUACAO' else ctx['saudacao'] + '!' } 
    
    Anotei aqui:
    🛒 *Mercado* (R$ 20,00)
    
    ✅ Salvo na planilha!"

    ----------------------------------
    INSTRUÇÃO DE TOM ATUAL: {ctx['instrucao']}
    """

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": texto_usuario}
    ]

    try:
        response = client.chat.completions.create(
            model="meta-llama/Llama-3.3-70B-Instruct-Turbo", 
            messages=messages,
            temperature=0.1, 
            max_tokens=300
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Erro no sistema: {str(e)}"

@app.route("/webhook", methods=['POST'])
def bot():
    msg_usuario = request.values.get('Body', '')
    user_id = request.values.get('From', 'desconhecido')
    
    print(f"Mensagem de {user_id}: {msg_usuario}")

    resultado = processar_mensagem(msg_usuario, user_id)
    
    resp = MessagingResponse()
    msg = resp.message()
    msg.body(resultado)

    return str(resp)

if __name__ == "__main__":
    app.run(port=5000, debug=True)