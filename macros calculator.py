meal_data = dict()

print("Are you calculating the macros of an ingredient or a meal?")
selection = input("Enter 'I' for Ingredient or 'M' for meal: ")

if selection == 'M' or selection == 'm':
    
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
        name = input("Enter the name of the meal: ")
        meal_data[name] = (total_calories, total_protein)

elif selection == 'I' or selection == 'i':
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
                name = input("Enter the name of the meal: ")
                meal_data[name] = (total_calories, total_protein) 

            terminate = True
