weight = float(input("Enter the weight in grams: "))
serving_size = float(input("Enter the serving size: "))
calories = float(input("Enter the calories per serving: "))
protein = float(input("Enter the amount of protein per serving: "))

total_calories = weight/serving_size*calories
total_protein = weight/serving_size*protein

print("Calories: ", total_calories, "\n Protein: ", total_protein)