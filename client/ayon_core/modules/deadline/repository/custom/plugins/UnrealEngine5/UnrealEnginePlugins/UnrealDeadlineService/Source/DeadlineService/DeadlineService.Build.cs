// Copyright Epic Games, Inc. All Rights Reserved.

using UnrealBuildTool;

public class DeadlineService : ModuleRules
{
	public DeadlineService(ReadOnlyTargetRules Target) : base(Target)
	{

		PrivateDependencyModuleNames.AddRange(
			new string[] {
				"AssetDefinition",
				"Core",
				"CoreUObject",
				"EditorStyle",
				"Engine",
				"DeveloperSettings",
				"UnrealEd",
				"JsonUtilities",
				"PropertyEditor",
				"SlateCore",
				"Slate"
			}
		);
	}
}
