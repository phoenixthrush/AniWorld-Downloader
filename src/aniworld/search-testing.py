import npyscreen
import requests
from urllib.parse import quote

class SearchForm(npyscreen.ActionForm):
    def create(self):
        self.search_box = self.add(npyscreen.TitleText, name="Search for a series:")
        self.add(npyscreen.ButtonPress, name="Search", when_pressed_function=self.fetch_results)

    def fetch_results(self):
        keyword = self.search_box.value
        encoded_keyword = quote(keyword)
        url = f"https://aniworld.to/ajax/seriesSearch?keyword={encoded_keyword}"
        response = requests.get(url)
        self.data = response.json()

        results = [f"{item['name']} ({item['productionYear']})" for item in self.data]
        self.parentApp.results = results
        self.parentApp.switchForm("RESULT")

class ResultForm(npyscreen.ActionForm):
    def create(self):
        self.result_list = self.add(npyscreen.MultiLineAction, max_height=10, values=[], scroll_exit=True)
        self.result_list.add_handlers({
            "k": self.result_list.h_exit_up,
            "j": self.result_list.h_exit_down
        })

    def beforeEditing(self):
        if hasattr(self.parentApp, 'results'):
            self.result_list.values = self.parentApp.results

    def on_ok(self):
        selected_index = self.result_list.value
        if selected_index is not None:
            selected_item = self.parentApp.results[selected_index]
            selected_name = selected_item.split(" (")[0]
            selected_link = next(item['link'] for item in self.parentApp.data if item['name'] == selected_name)
            print(f"Selected series link: {selected_link}")
        self.parentApp.setNextForm(None)

    def on_cancel(self):
        self.parentApp.setNextForm(None)

class SearchApp(npyscreen.NPSAppManaged):
    def onStart(self):
        self.addForm("MAIN", SearchForm)
        self.addForm("RESULT", ResultForm)

if __name__ == "__main__":
    app = SearchApp()
    app.run()
