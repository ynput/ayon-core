// Copyright Epic Games, Inc. All Rights Reserved.

using UnrealBuildTool;

public class MoviePipelineDeadline : ModuleRules
{
	public MoviePipelineDeadline(ReadOnlyTargetRules Target) : base(Target)
	{
		ShortName = "DMP";

		PrivateDependencyModuleNames.AddRange(
			new string[] {
				"Core",
				"CoreUObject",
				"DeadlineService",
				"DeveloperSettings",
				"Engine",
				"InputCore",
				"MovieRenderPipelineCore",
				"PropertyEditor",
				"RenderCore",
				"Slate",
				"SlateCore"
			}
		);

		PublicDependencyModuleNames.AddRange(
			new string[] {
            }
        );
	}
}
