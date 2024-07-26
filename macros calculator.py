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

def format_float(value):
    return round(value, 2)

valid = False
while not valid:
    try:
        print("Do you want to calculate the macros of a single item or multiple items?")
        selection = input("Enter 'S' for single item or 'M' for multiple items: ")
        if selection not in ['S','s','M','m']:
            raise ValueError
        valid = True
    except ValueError:
        print("Error: Please enter 'S' or 'M' as input!")

if selection == 'S' or selection == 's':
    
    weight = float(input("Enter the weight in grams: "))
    
    valid = False
    while not valid:
        try:
            serving_size = float(input("Enter the serving size: "))
            if serving_size == 0:
                raise ZeroDivisionError
            valid = True
        except ZeroDivisionError:
            print("Error: serving size cannot be zero!")

    calories = float(input("Enter the calories per serving: "))
    protein = float(input("Enter the amount of protein per serving: "))

    total_calories = format_float(weight/serving_size*calories)
    total_protein = format_float(weight/serving_size*protein)

    print("Calories: ", total_calories, "\nProtein: ", total_protein)

    print("Do you want to save this meal?")
    
    valid = False
    while not valid:
        try:
            save = input("Enter 'Y' for yes or 'N' for no: ")
            if save not in ['Y','y','N','n']:
                raise ValueError
            valid = True
        except ValueError:
            print("Error: Please enter 'Y' or 'N' as input!")

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

        valid = False
        while not valid:
            try:
                serving_size = float(input("Enter the serving size: "))
                if serving_size == 0:
                    raise ZeroDivisionError
                valid = True
            except ZeroDivisionError:
                print("Error: serving size cannot be zero!")

        calories = float(input("Enter the calories per serving: "))
        protein = float(input("Enter the amount of protein per serving: "))
            
        current_calories = format_float(weight/serving_size*calories)
        current_protein = format_float(weight/serving_size*protein)
        total_calories += format_float(current_calories)
        total_protein += format_float(current_protein)

        print("Calories (Ingredient): ", current_calories, "\nProtein (Ingredient): ", current_protein)

        print("Do you want to add another ingredient?")
        
        valid = False
        while not valid:
            try:
                addition = input("Enter 'Y' for yes or 'N' for no: ")
                if addition not in ['Y','y','N','n']:
                    raise ValueError
                valid = True
            except ValueError:
                print("Error: Please enter 'Y' or 'N' as input!")

        if addition == 'Y' or addition == 'y':
            terminate = False
        elif addition == 'N' or addition == 'n':
            print("Total Calories: ", total_calories, "\nTotal Protein: ", total_protein)

            print("Do you want to save this meal?")
            
            valid = False
            while not valid:
                try:
                    save = input("Enter 'Y' for yes or 'N' for no: ")
                    if save not in ['Y','y','N','n']:
                        raise ValueError
                    valid = True
                except ValueError:
                    print("Error: Please enter 'Y' or 'N' as input!")
            
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
