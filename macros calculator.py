import json
from datetime import datetime

meal_data = dict()
current_meal = dict()
total_intake_data = dict()
current_intake_data = dict()

def load_data():
    global meal_data, total_intake_data    

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


    try:
        file =  open('total_intake_data.txt', 'x')
    except FileExistsError:
        pass

    try: 
        if len(total_intake_data) == 0:
            with open('total_intake_data.txt') as Input:
                total_intake_data = json.load(Input)
    except ValueError: 
        pass

    return meal_data, total_intake_data

def save_meal(name, date, total_calories, total_protein):
    if date in meal_data: 
        current_meal = meal_data[date]
    else: 
        current_meal = {}

    current_meal[name] = [total_calories, total_protein] 
    meal_data[date] = current_meal
    print(meal_data)

    with open('Meal_Data.txt', 'w') as Output: 
        json.dump(meal_data, Output, indent=4)

def format_float(value):
    return round(value, 2)

def calculate_macros():
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
def main():
    shutdown = False
    while not shutdown:
        print("Welcome to the Macros Calculator!")
        print("What do you wish to do today?")
        print("---------------------------------")
        print("1. Calculate Macros")
        print("2. Display Stored Meals")
        print("3. Display total Calorie and Protein Intake")
        print("4. Calculate Average Calorie and Protein Intake")
        command = input("Type the corresponding number to select the option: ")
        
        if command == "1":
            calculate_macros()
            shutdown = True
        
        elif command == "2":
            select_date = input("Enter the date of which you wish to view stored meals in (Day-Month-Year) format: ")
            if select_date in meal_data:
                for meal in meal_data[select_date]:
                    print(meal, ": ", meal_data[select_date][meal][0], ",", meal_data[select_date][meal][1])
            else:
                print("The given date does not exist!")
            shutdown = True

        elif command == "3":
            total_calorie_intake = 0
            total_protein_intake = 0
            select_date = input("Enter the date of which you wish to view total calorie and protein intake in (Day-Month-Year) format: ")
            if select_date in meal_data:
                for meals in meal_data[select_date]:
                    total_calorie_intake += meal_data[select_date][meals][0]
                for meals in meal_data[select_date]:
                    total_protein_intake += meal_data[select_date][meals][1]
                print("The total calorie intake for the given date is: ",total_calorie_intake)
                print("The total protein intake for the given date is: ",total_protein_intake)
                print("Do you want to store this data?")
                valid = False
                while not valid:
                    try:
                        save = input("Enter 'Y' for yes or 'N' for no: ")
                        if save not in ['Y','y','N','n']:
                            raise ValueError
                        valid = True
                    except ValueError:
                        print("Error: Please enter 'Y' or 'N' as input!")
                if save == 'N' or save =='n':
                    shutdown = True
                elif save == 'Y' or save == "y":
                    date = input("Enter the date in (Day-Month-Year) format: ")
                    if date in total_intake_data:
                        print("This date already exists!")
                        print("Do you want to overwrite this date?")
                        valid = False
                        while not valid:
                            try:
                                save = input("Enter 'Y' for yes or 'N' for no: ")
                                if save not in ['Y','y','N','n']:
                                    raise ValueError
                                valid = True
                            except ValueError:
                                print("Error: Please enter 'Y' or 'N' as input!")
                        if save == 'Y' or save == "y":
                            total_intake_data[date] = [total_calorie_intake,total_protein_intake]
                            print(total_intake_data)
                            with open('total_intake_data.txt', 'w') as Output:
                                json.dump(total_intake_data, Output, indent=4)
                    else:
                        total_intake_data[date] = [total_calorie_intake,total_protein_intake]
                        print(total_intake_data)
                        with open('total_intake_data.txt', 'w') as Output:
                            json.dump(total_intake_data, Output, indent=4) 
            elif select_date not in total_intake_data:
                print("The given date does not exist!")
            shutdown = True

        elif command == '4':
            
            start_date = input("Enter the start date in (Day-Month-Year) format: ")
            end_date = input("Enter the end date in (Day-Month-Year) format: ")
            if start_date not in total_intake_data:
                print("The given start date does not exist!")
            elif end_date not in total_intake_data:
                print("The given end date does not exist!")
            else:
                start_date = datetime.strptime(start_date, "%d-%m-%Y")
                end_date = datetime.strptime(end_date, "%d-%m-%Y")
                filtered_data = {date: values for date, values in total_intake_data.items() if start_date <= datetime.strptime(date, "%d-%m-%Y") <= end_date}
                total_calories = sum(values[0] for values in filtered_data.values())
                total_protein = sum(values[1] for values in filtered_data.values())
                days = len(filtered_data)
                if days == 0:
                    print("Error: The start date and end date are the same values!")
                else:
                    average_calories = total_calories / days
                    average_protein = total_protein / days
                    print(f"Average Calories: {average_calories:.2f}")
                    print(f"Average Protein: {average_protein:.2f}")
            shutdown = True
    
if __name__ == "__main__":
    main()
