import base64
import re
import warnings
from datetime import datetime
from urllib.parse import urljoin

from odoo import http
from odoo.http import request
from odoo.tools.translate import _

# Only use for behavior, don't stock it
# Used to filter the session dict to keep only the form fields
_TECHNICAL = ["view_from", "view_callback"]
# Allow in description
_BLACKLIST = [
    "id",
    "create_uid",
    "create_date",
    "write_uid",
    "write_date",
    "user_id",
    "active",
]

_COOP_FORM_FIELD = [
    "email",
    "confirm_email",
    "firstname",
    "lastname",
    "birthdate",
    "iban",
    "share_product_id",
    "address",
    "city",
    "zip_code",
    "country_id",
    "phone",
    "lang",
    "nb_parts",
    "total_parts",
    "error_msg",
]

_COMPANY_FORM_FIELD = [
    "is_company",
    "company_register_number",
    "company_name",
    "company_email",
    "confirm_email",
    "email",
    "firstname",
    "lastname",
    "birthdate",
    "iban",
    "share_product_id",
    "address",
    "city",
    "zip_code",
    "country_id",
    "phone",
    "lang",
    "nb_parts",
    "total_parts",
    "error_msg",
    "company_type",
]


class WebsiteSubscription(http.Controller):
    @http.route(
        ["/page/become_cooperator", "/become_cooperator"],
        type="http",
        auth="public",
        website=True,
    )
    def display_become_cooperator_page(self, **kwargs):
        values = {}
        logged = False
        if request.env.user.login != "public":
            logged = True
            partner = request.env.user.partner_id
            if partner.is_company:
                return self.display_become_company_cooperator_page()
        values = self.fill_values(values, False, logged, True)

        for field in _COOP_FORM_FIELD:
            if kwargs.get(field):
                values[field] = kwargs.pop(field)

        values.update(kwargs=kwargs.items())
        # redirect url to fall back on become cooperator in template redirection
        values["redirect_url"] = request.httprequest.url
        return request.render("cooperator_website.becomecooperator", values)

    @http.route(
        ["/page/become_company_cooperator", "/become_company_cooperator"],
        type="http",
        auth="public",
        website=True,
    )
    def display_become_company_cooperator_page(self, **kwargs):
        values = {}
        logged = False

        if request.env.user.login != "public":
            logged = True
        values = self.fill_values(values, True, logged, True)

        for field in _COMPANY_FORM_FIELD:
            if kwargs.get(field):
                values[field] = kwargs.pop(field)
        values.update(kwargs=kwargs.items())
        return request.render("cooperator_website.becomecompanycooperator", values)

    def pre_render_thanks(self, values, kwargs):
        """
        Allows to modify values passed to the "thanks" template by overriding
        this method.
        """
        return {"_values": values, "_kwargs": kwargs}

    def preRenderThanks(self, values, kwargs):
        warnings.warn(
            "WebsiteSubscription.preRenderThanks() is deprecated. "
            "please use .pre_render_thanks() instead.",
            DeprecationWarning,
        )
        return self.pre_render_thanks(values, kwargs)

    def get_subscription_response(self, values, kwargs):
        values = self.pre_render_thanks(values, kwargs)
        return request.render("cooperator_website.cooperator_thanks", values)

    def get_date_string(self, birthdate):
        if birthdate:
            return datetime.strftime(birthdate, "%Y-%m-%d")
        return False

    def get_values_from_user(self, values, is_company):
        # the subscriber is connected
        if request.env.user.login != "public":
            values["logged"] = "on"
            partner = request.env.user.partner_id

            if partner.member or partner.old_member:
                values["already_cooperator"] = "on"
            if partner.bank_ids:
                values["iban"] = partner.bank_ids[0].acc_number
            values["address"] = partner.street
            values["zip_code"] = partner.zip
            values["city"] = partner.city
            values["country_id"] = partner.country_id.id

            if is_company:
                # company values
                values["company_register_number"] = partner.company_register_number
                values["company_name"] = partner.name
                values["company_email"] = partner.email
                values["company_type"] = partner.legal_form
                # contact person values
                representative = partner.get_representative()
                values["firstname"] = representative.firstname
                values["lastname"] = representative.lastname
                values["gender"] = representative.gender
                values["email"] = representative.email
                values["contact_person_function"] = representative.function
                values["birthdate"] = self.get_date_string(
                    representative.birthdate_date
                )
                values["lang"] = representative.lang
                values["phone"] = representative.phone
            else:
                values["firstname"] = partner.firstname
                values["lastname"] = partner.lastname
                values["email"] = partner.email
                values["gender"] = partner.gender
                values["birthdate"] = self.get_date_string(partner.birthdate_date)
                values["lang"] = partner.lang
                values["phone"] = partner.phone
        return values

    def fill_values(self, values, is_company, logged, load_from_user=False):
        sub_req_obj = request.env["subscription.request"]
        company = request.website.company_id
        products = self.get_products_share(is_company)

        if load_from_user:
            values = self.get_values_from_user(values, is_company)
        if is_company:
            values["is_company"] = "on"
        if logged:
            values["logged"] = "on"
        values["countries"] = self.get_countries()
        values["langs"] = self.get_langs()
        values["products"] = products
        fields_desc = sub_req_obj.sudo().fields_get(["company_type", "gender"])
        values["company_types"] = fields_desc["company_type"]["selection"]
        values["genders"] = fields_desc["gender"]["selection"]
        values["company"] = company

        if not values.get("share_product_id"):
            for product in products:
                if product.default_share_product is True:
                    values["share_product_id"] = product.id
                    break
            if not values.get("share_product_id", False) and products:
                values["share_product_id"] = products[0].id
        if not values.get("country_id"):
            if company.default_country_id:
                values["country_id"] = company.default_country_id.id
            else:
                values["country_id"] = "20"
        if not values.get("activities_country_id"):
            if company.default_country_id:
                values["activities_country_id"] = company.default_country_id.id
            else:
                values["activities_country_id"] = "20"
        if not values.get("lang"):
            if company.default_lang_id:
                values["lang"] = company.default_lang_id.code

        values.update(
            {
                "display_data_policy": company.display_data_policy_approval,
                "data_policy_required": company.data_policy_approval_required,
                "data_policy_text": company.data_policy_approval_text,
                "display_internal_rules": company.display_internal_rules_approval,
                "internal_rules_required": company.internal_rules_approval_required,
                "internal_rules_text": company.internal_rules_approval_text,
                "display_financial_risk": company.display_financial_risk_approval,
                "financial_risk_required": company.financial_risk_approval_required,
                "financial_risk_text": company.financial_risk_approval_text,
                "display_generic_rules": company.display_generic_rules_approval,
                "generic_rules_required": company.generic_rules_approval_required,
                "generic_rules_text": company.generic_rules_approval_text,
            }
        )
        return values

    def get_products_share(self, is_company):
        product_obj = request.env["product.template"]
        products = product_obj.sudo().get_web_share_products(is_company)

        return products

    def get_countries(self):
        countries = request.env["res.country"].sudo().search([])

        return countries

    def get_langs(self):
        langs = request.env["res.lang"].sudo().search([])
        return langs

    def get_selected_share(self, kwargs):
        prod_obj = request.env["product.template"]
        product_id = kwargs.get("share_product_id")
        return prod_obj.sudo().browse(int(product_id)).product_variant_ids[0]

    def _additional_validate(self, kwargs, logged, values, post_file):
        """
        Validation hook that can be reimplemented in dependent modules.

        This should return a boolean value indicating whether the validation
        succeeded or not. If it did not succeed, an error message should be
        assigned to values["error_msg"].
        """
        return True

    def validation(  # noqa: C901 (method too complex)
        self, kwargs, logged, values, post_file
    ):
        user_obj = request.env["res.users"]
        sub_req_obj = request.env["subscription.request"]

        redirect = "cooperator_website.becomecooperator"

        # url to use for "already have an account button" to go to become cooperator
        # rather than subscribe share after a failed validation
        # it is deleted at the end of the validation
        values["redirect_url"] = urljoin(
            request.httprequest.host_url, "become_cooperator"
        )

        email = kwargs.get("email")
        is_company = kwargs.get("is_company") == "on"

        if is_company:
            is_company = True
            redirect = "cooperator_website.becomecompanycooperator"
            email = kwargs.get("company_email")
        # Check that required field from model subscription_request exists
        required_fields = sub_req_obj.sudo().get_required_field()
        error = {field for field in required_fields if not values.get(field)}  # noqa

        if error:
            values = self.fill_values(values, is_company, logged)
            values["error_msg"] = _("Some mandatory fields have not been filled.")
            values = dict(values, error=error, kwargs=kwargs.items())
            return request.render(redirect, values)

        if not logged and email:
            user = user_obj.sudo().search([("login", "=", email)])
            if user:
                values = self.fill_values(values, is_company, logged)
                values.update(kwargs)
                values["error_msg"] = _(
                    "An account already exists for this email address. "
                    "Please log in before filling in the form."
                )

                return request.render(redirect, values)
            else:
                confirm_email = kwargs.get("confirm_email")
                if email != confirm_email:
                    values = self.fill_values(values, is_company, logged)
                    values.update(kwargs)
                    values["error_msg"] = _(
                        "Email and confirmation email addresses don't match."
                    )
                    return request.render(redirect, values)

        # There's no issue with the email, so we can remember the confirmation email
        values["confirm_email"] = email

        company = request.website.company_id
        if company.allow_id_card_upload:
            if not post_file:
                values = self.fill_values(values, is_company, logged)
                values.update(kwargs)
                values["error_msg"] = _("Please upload a scan of your ID card.")
                return request.render(redirect, values)

        if "iban" in required_fields:
            iban = kwargs.get("iban")
            if iban.strip():
                valid = sub_req_obj.check_iban(iban)

                if not valid:
                    values = self.fill_values(values, is_company, logged)
                    values["error_msg"] = _("Provided IBAN is not valid.")
                    return request.render(redirect, values)

        # check the subscription's amount
        max_amount = company.subscription_maximum_amount
        if logged:
            partner = request.env.user.partner_id
            if partner.member:
                max_amount = max_amount - partner.total_value
                if company.unmix_share_type:
                    share = self.get_selected_share(kwargs)
                    if partner.cooperator_type != share.default_code:
                        values = self.fill_values(values, is_company, logged)
                        values["error_msg"] = _(
                            "You can't subscribe to two different types of share."
                        )
                        return request.render(redirect, values)
        total_amount = float(kwargs.get("total_parts"))

        if max_amount > 0 and total_amount > max_amount:
            values = self.fill_values(values, is_company, logged)
            values["error_msg"] = _(
                "You can't subscribe for an amount that exceeds "
                "{amount}{currency_symbol}."
            ).format(amount=max_amount, currency_symbol=company.currency_id.symbol)
            return request.render(redirect, values)

        if not self._additional_validate(kwargs, logged, values, post_file):
            values = self.fill_values(values, is_company, logged)
            return request.render(redirect, values)

        # remove non-model attributes (used internally when re-rendering the
        # form in case of a validation error)
        del values["redirect_url"]
        del values["confirm_email"]

        return True

    @http.route(
        ["/subscription/get_share_product"],
        type="json",
        auth="public",
        methods=["POST"],
        website=True,
    )
    def get_share_product(self, share_product_id, **kw):
        product_template = request.env["product.template"]
        product = product_template.sudo().browse(int(share_product_id))
        return {
            product.id: {
                "list_price": product.list_price,
                "min_qty": product.minimum_quantity,
                "force_min_qty": product.force_min_qty,
            }
        }

    @http.route(  # noqa: C901 (method too complex)
        ["/subscription/subscribe_share"],
        type="http",
        auth="public",
        website=True,
    )  # noqa: C901 (method too complex)
    def share_subscription(self, **kwargs):  # noqa: C901 (method too complex)
        sub_req_obj = request.env["subscription.request"]
        attach_obj = request.env["ir.attachment"]

        # List of file to add to ir_attachment once we have the ID
        post_file = []
        # Info to add after the message
        post_description = []
        values = {}

        for field_name, field_value in kwargs.items():
            if hasattr(field_value, "filename"):
                post_file.append(field_value)
            elif field_name in sub_req_obj._fields and field_name not in _BLACKLIST:
                values[field_name] = field_value
            # allow to add some free fields or blacklisted field like ID
            elif field_name not in _TECHNICAL:
                post_description.append("{}: {}".format(field_name, field_value))

        logged = kwargs.get("logged") == "on"
        is_company = kwargs.get("is_company") == "on"

        response = self.validation(kwargs, logged, values, post_file)
        if response is not True:
            return response

        already_coop = False
        if logged:
            partner = request.env.user.partner_id
            values["partner_id"] = partner.id
            already_coop = partner.member
        elif kwargs.get("already_cooperator") == "on":
            already_coop = True

        values["already_cooperator"] = already_coop
        values["is_company"] = is_company

        if kwargs.get("data_policy_approved", "off") == "on":
            values["data_policy_approved"] = True

        if kwargs.get("internal_rules_approved", "off") == "on":
            values["internal_rules_approved"] = True

        if kwargs.get("financial_risk_approved", "off") == "on":
            values["financial_risk_approved"] = True
        if kwargs.get("generic_rules_approved", "off") == "on":
            values["generic_rules_approved"] = True

        lastname = kwargs.get("lastname")
        firstname = kwargs.get("firstname")

        values["lastname"] = lastname
        values["firstname"] = firstname
        values["birthdate"] = datetime.strptime(
            kwargs.get("birthdate"), "%Y-%m-%d"
        ).date()
        values["source"] = "website"

        values["share_product_id"] = self.get_selected_share(kwargs).id

        if is_company:
            if kwargs.get("company_register_number"):
                values["company_register_number"] = re.sub(
                    "[^0-9a-zA-Z]+", "", kwargs.get("company_register_number")
                )

        subscription_id = sub_req_obj.sudo().create(values)

        if subscription_id:
            for field_value in post_file:
                attachment_value = {
                    "name": field_value.filename,
                    "res_name": field_value.filename,
                    "res_model": "subscription.request",
                    "res_id": subscription_id,
                    "datas": base64.encodestring(field_value.read()),
                    "datas_fname": field_value.filename,
                }
                attach_obj.sudo().create(attachment_value)

        return self.get_subscription_response(values, kwargs)
