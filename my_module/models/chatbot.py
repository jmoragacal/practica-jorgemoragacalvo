from odoo import models
from html import unescape
import requests
import logging
import re
import time

_logger = logging.getLogger(__name__)
_logger.info("=== CHATBOT MODULE LOADING ===")

class DiscussChannel(models.Model):
    _inherit = 'discuss.channel'

    def _get_task_context(self):
        try:
            ProjectTask = self.env['project.task']
            tasks = ProjectTask.search([('active', '=', True)])

            if not tasks:
                return "No hay tareas registradas en el sistema."

            context = f"Tienes {len(tasks)} tareas activas:\n\n"
            for i, task in enumerate(tasks, 1):
                nombre = task.name or "Sin nombre"
                estado = dict(task._fields['state'].selection).get(task.state, task.state)
                fecha_creacion = task.create_date.strftime("%d-%m-%Y") if task.create_date else "Sin fecha"
                fecha_actualizacion = task.write_date.strftime("%d-%m-%Y") if task.write_date else "Sin fecha"
                prioridad = dict(task._fields['priority'].selection).get(task.priority, task.priority)
                asignados = ", ".join(task.user_ids.mapped('name')) or "Sin asignar"
                vencimiento = task.date_deadline.strftime("%d-%m-%Y") if task.date_deadline else "Sin fecha"
                proyecto = task.project_id.name or "Sin proyecto"

                context += f"""- {nombre} | Estado: {estado} | Creación {fecha_creacion} | Actualización {fecha_actualizacion}
                | Prioridad: {prioridad} | Asignado a: {asignados} | Vence: {vencimiento} | Proyecto: {proyecto}\n"""

            return context.strip()
        except Exception as e:
            _logger.error("Error getting task context: %s", str(e))
            return "Error al obtener el contexto de tareas."

    # Obtener mensaje del usuario en el chat
    def _message_post_after_hook(self, message, msg_vals):
        result = super()._message_post_after_hook(message, msg_vals)

        ai_partner = self.env.ref('chatbot_ai.ai_assistant_partner', raise_if_not_found=False)
        if ai_partner and message.author_id != ai_partner:
        #if message.author_id != self.env.ref('chatbot_ai.ai_assistant_partner'):
            self._handle_ai_response(message)

        return result

    # Manejar respuesta del chatbot
    def _handle_ai_response(self, message):
        try:
            _logger.info("Mensaje recibido del usuario")

            api_key = self.env['ir.config_parameter'].sudo().get_param(
                'chatbot_ai.gemini_api_key', None)

            if not api_key:
                _logger.error("No se encontró la clave API de Gemini.")
                #
                self.sudo().message_post(
                body="Error: No se ha configurado la clave API de Gemini.",
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
                author_id=self.env.ref('chatbot_ai.ai_assistant_partner').id
                )
                #
                return

            task_context = self._get_task_context()

            system_prompt = (
                "Eres un asistente experto en tareas de Odoo. "
                "Usa el contexto proporcionado para responder con claridad y precisión. "
                "Responde en texto claro sin formatos y de manera ordenada, "
                "de forma que la respuesta se entienda de manera fácil"
            )

            # Obtener historial de mensajes para contexto
            domain = [
                ('model', '=', 'discuss.channel'),
                ('res_id', '=', self.id),
                ('message_type', '=', 'comment')
            ]
            history = self.env['mail.message'].search(domain, limit=10, order='id desc')

            # Construir historial de conversación con roles adecuados
            parts = [{"role": "user", "parts": [{"text": f"Contexto:\n{task_context}"}]}]
            #assistant_partner = self.env.ref('chatbot_ai.ai_assistant_partner')
            assistant_partner = self.env.ref('chatbot_ai.ai_assistant_partner', raise_if_not_found=False)
            
            if not assistant_partner:
                #
                _logger.error("No se encontró el partner del asistente AI.")
                self.sudo().message_post(
                body="Error: No se encontró el partner del asistente AI.",
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
                author_id=self.env.ref('base.partner_admin').id
                )
                #
                return

            # Construir historial de conversación con roles adecuados
            parts = [{"role": "user", "parts": [{"text": f"Contexto:\n{task_context}"}]}]
            for m in reversed(history):
                role = "model" if m.author_id == assistant_partner else "user"
                text = clean_html(m.body.strip())
                if text:
                    parts.append({"role": role, "parts": [{"text": text}]})

            # Agregar el nuevo mensaje del usuario
            user_prompt = message.body.strip()
            _logger.info("Contenido del mensaje del usuario sin limpiar: %s", user_prompt)
            user_prompt_clean = clean_html(user_prompt)
            _logger.info("Contenido del mensaje del usuario limpiado: %s", user_prompt_clean)

            parts.append({"role": "user", "parts": [{"text": user_prompt_clean}]})

            payload = {
                "system_instruction": {"parts": [{"text": system_prompt}]},
                "contents": parts
            }

            headers = {
                "Content-Type": "application/json",
                "x-goog-api-key": api_key
            }

            # Enviar mensaje a la api rest de gemini
            response = requests.post( "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-05-20:generateContent",
                headers=headers,
                json=payload
            )

            # Mostrar respuesta de la api en el chatbot
            if response.status_code == 200:
                data = response.json()
                if "candidates" in data and data["candidates"]:
                    raw_ai_message = response.json()["candidates"][0]["content"]["parts"][0]["text"]
                    _logger.info("Respuesta sin limpiar: %s", raw_ai_message)

                    max_retries = 3
                    for attempt in range(max_retries):
                        try:
                            self.sudo().message_post(
                                body=raw_ai_message,
                                message_type='comment',
                                subtype_xmlid='mail.mt_comment',
                                author_id=self.env.ref('chatbot_ai.ai_assistant_partner').id,
                            )
                            _logger.info("Mensaje del bot enviado exitosamente en el intento %s", attempt + 1)
                            break
                        except Exception as e:
                            _logger.warning(f"Intento {attempt + 1} fallido al enviar mensaje del bot: {str(e)}")
                            time.sleep(0.5)  # Espera antes de intentar de nuevo
                else:
                    # Esto se ejecuta si el bucle termina sin 'break', es decir, todos los intentos fallaron
                    _logger.error("Fallo final: No se pudo enviar el mensaje del bot tras %s intentos.", max_retries)
                    self.sudo().message_post(
                        body="Error: No se pudo enviar la respuesta del bot. Intenta de nuevo.",
                        message_type='comment',
                        subtype_xmlid='mail.mt_comment',
                        author_id=assistant_partner.id
                    )
            else:
                _logger.error("Gemini API error: %s", response.text)
                self.sudo().message_post(
                body="Error: Fallo al conectar con la API de Gemini.",
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
                author_id=assistant_partner.id
                )

        except Exception as e:
            _logger.error("Error al generar respuesta del chatbot: %s", str(e))
            self.sudo().message_post(
            body="Error: Ocurrió un problema al procesar la solicitud. Intenta de nuevo.",
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
            author_id=assistant_partner.id
            )

# Método para limpiar el mensaje html
def clean_html(raw_html):
    clean = re.compile('<.*?>')
    return unescape(re.sub(clean, '', raw_html))