from django.http import HttpResponseBadRequest
from django.shortcuts import render
from django.urls import path
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django.views import View

from .core import AC_CLASS_CONFIGURABLE_VALUES, ContextArg, _ac_registry


class AutocompleteBaseView(View):
    @cached_property
    def ac_class(self):
        ac_name = self.kwargs["ac_name"]

        try:
            return _ac_registry[ac_name]

        except KeyError as e:
            raise ValueError(f"No registered autocomplete with name {ac_name}") from e

    def dispatch(self, request, *args, **kwargs):
        self.ac_class.auth_check(request)

        return super().dispatch(request, *args, **kwargs)

    def get_items(self, item_keys):
        return self.ac_class.get_items_from_keys(item_keys)

    @cached_property
    def request_dict(self):
        # convert the request's QueryDict into a regular dict
        return self.request.GET.dict()

    def get_field_name(self):
        return self.request_dict["field_name"]

    def get_component_id(self):
        prefix = self.get_configurable_value("component_prefix")

        return prefix + self.get_field_name()

    def get_configurable_value(self, key):
        if key in self.request_dict:
            return self.request.GET.get(key)

        if key in AC_CLASS_CONFIGURABLE_VALUES and hasattr(self.ac_class, key):
            return getattr(self.ac_class, key)

        return None

    def get_custom_strings(self):
        return {
            "no_results": self.ac_class.no_result_text,
            "more_results": self.ac_class.narrow_search_text,
        }

    def get_template_context(self):
        # many things will come from the request
        # others will be picked up from the AC class

        return {
            "route_name": self.ac_class.route_name,
            #
            "field_name": self.get_field_name(),
            "component_id": self.get_component_id(),
            "required": bool(self.get_configurable_value("required")),
            "placeholder": self.get_configurable_value("placeholder"),
            "indicator": self.get_configurable_value("indicator"),
            "custom_strings": self.ac_class.get_custom_strings(),
            "multiselect": bool(self.get_configurable_value("multiselect")),
            "component_prefix": self.get_configurable_value("component_prefix"),
            "disabled": bool(self.get_configurable_value("disabled")),
        }


class ToggleView(AutocompleteBaseView):
    def get(self, request, *args, **kwargs):
        field_name = self.request_dict["field_name"]

        current_items = self.request.GET.getlist(field_name)
        if current_items == ["undefined"] or current_items == [""]:
            current_items = []

        key_to_toggle = request.GET.get("item")

        if key_to_toggle is None:
            return HttpResponseBadRequest()

        new_selected_keys = list(current_items)

        is_multi = self.get_configurable_value("multiselect")

        if is_multi:
            if key_to_toggle in current_items:
                new_selected_keys.remove(key_to_toggle)
            else:
                new_selected_keys.append(key_to_toggle)
        else:
            if new_selected_keys == []:
                new_selected_keys = [key_to_toggle]
            else:
                new_selected_keys = []

        keys_to_fetch = set(new_selected_keys).union({key_to_toggle})

        context_obj = ContextArg(request=request, client_kwargs=request.GET)
        all_values = self.ac_class.get_items_from_keys(keys_to_fetch, context_obj)

        items = self.ac_class.map_search_results(all_values, new_selected_keys)

        # OOB is used if the user clicks the X on a chip,
        # to update the selected style of the option
        # if it is currently in the dropdown list
        swap_oob = request.GET.get("remove", False)

        target_item = next((x for x in items if x["key"] == key_to_toggle), None)

        new_items = [x for x in items if x["key"] in new_selected_keys]

        def sort_items(item):
            try:
                print(item, current_items.index(f"{item['key']}"))
                return current_items.index(f"{item['key']}")
            except ValueError:
                print(item, len(current_items))
                return len(new_items)

        new_items = sorted(new_items, key=sort_items)

        if target_item is None:
            raise ValueError("Requested item to toggle not found.")

        return render(
            request,
            "autocomplete/item.html",
            {
                **self.get_template_context(),
                "search": "",
                "values": new_selected_keys,
                "item_as_list": [target_item],
                "item": target_item,
                "toggle": new_items,
                "swap_oob": swap_oob,
            },
        )


class ItemsView(AutocompleteBaseView):
    def get(self, request, *args, **kwargs):
        context_obj = ContextArg(request=request, client_kwargs=request.GET)

        search_query = request.GET.get("search", "")
        search_results = self.ac_class.search_items(
            # or whatever
            search_query,
            context_obj,
        )

        field_name = self.get_configurable_value("field_name")
        selected_keys = request.GET.getlist(field_name)

        show = len(search_query) >= self.ac_class.minimum_search_length

        total_results = len(search_results)
        if len(search_results) > self.ac_class.max_results:
            search_results = search_results[: self.ac_class.max_results]

        items = self.ac_class.map_search_results(search_results, selected_keys)

        # render items ...
        return render(
            request,
            "autocomplete/item_list.html",
            {
                # note: name -> field_name
                **self.get_template_context(),
                "show": show,
                "search": search_query,
                "items": items,
                "total_results": total_results,
            },
        )


urls = (
    [
        path("autocomplete/<str:ac_name>/items", ItemsView.as_view(), name="items"),
        path("autocomplete/<str:ac_name>/toggle", ToggleView.as_view(), name="toggle"),
    ],
    "autocomplete",
    "autocomplete",
)