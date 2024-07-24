import json
meal_data = dict()
current_meal = dict()

try:
    file =  open('Meal_Data.txt', 'x')
except FileExistsError:
    pass


try: 
    if len(meal_data) == 0:
        with open('Meal_Data.txt') as Input:
            meal_data = json.load(Input)
except ValueError: 
    pass


print("Do you want to calculate the macros of a single item or multiple items?")
selection = input("Enter 'S' for single item or 'M' for multiple items: ")

if selection == 'S' or selection == 's':
    
    weight = float(input("Enter the weight in grams: "))
    serving_size = float(input("Enter the serving size: "))
    calories = float(input("Enter the calories per serving: "))
    protein = float(input("Enter the amount of protein per serving: "))

    total_calories = weight/serving_size*calories
    total_protein = weight/serving_size*protein

    print("Calories: ", total_calories, "\nProtein: ", total_protein)

    print("Do you want to save this meal?")
    save = input("Enter 'Y' for yes or 'N' for no: ")
    if save == 'Y' or save == 'y':
        date = input("Enter the date in (Day-Month-Year) format: ")
        name = input("Enter the name of the meal: ")
        if date in meal_data: 
            current_meal = meal_data[date]
        else: 
            current_meal = {}

        current_meal[name] = [total_calories, total_protein] 
        meal_data[date] = current_meal
        print(meal_data)

        with open('Meal_Data.txt', 'w') as Output:
            json.dump(meal_data, Output, indent=4)

elif selection == 'M' or selection == 'm':
    terminate = False
    total_calories = 0
    total_protein = 0
    while not terminate:
        weight = float(input("Enter the weight in grams: "))
        serving_size = float(input("Enter the serving size: "))
        calories = float(input("Enter the calories per serving: "))
        protein = float(input("Enter the amount of protein per serving: "))
            
        current_calories = weight/serving_size*calories
        current_protein = weight/serving_size*protein
        total_calories += current_calories
        total_protein += current_protein

        print("Calories (Ingredient): ", current_calories, "\nProtein (Ingredient): ", current_protein)

        print("Do you want to add another ingredient?")
        addition = input("Enter 'Y' for yes or 'N' for no: ")
        if addition == 'Y' or addition == 'y':
            terminate = False
        elif addition == 'N' or addition == 'n':
            print("Total Calories: ", total_calories, "\nTotal Protein: ", total_protein)

            print("Do you want to save this meal?")
            save = input("Enter 'Y' for yes or 'N' for no: ")
            if save == 'Y' or save == 'y':
                date = input("Enter the date in (Day-Month-Year) format: ")
                name = input("Enter the name of the meal: ")
            if date in meal_data: 
                current_meal = meal_data[date]
            else: 
                current_meal = {}

            current_meal[name] = [total_calories, total_protein]
            meal_data[date] = current_meal
            print(meal_data)

            with open('Meal_Data.txt', 'w') as Output:
                json.dump(meal_data, Output, indent=4)

            terminate = True
