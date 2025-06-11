from odoo import api, fields, models

class WhatsappTemplate(models.Model):
    _inherit = 'whatsapp.template'

    is_calender_event = fields.Boolean(
        string='Is Calendar Event',
        help='Indicates if the template is used for calendar events.',
        default=False,
    )

    @api.onchange('is_calender_event')
    def on_change_template(self):
        if self.is_calender_event:
            old_selected = self.env['whatsapp.template'].search([('is_calender_event', '=', True)])
            if old_selected:
                old_selected.is_calender_event = False
