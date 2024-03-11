// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "Engine/DeveloperSettings.h"

#include "DeadlineJobPreset.h"

#include "MoviePipelineDeadlineSettings.generated.h"

/**
* Project-wide settings for Deadline Movie Pipeline.
*/
UCLASS(BlueprintType, config = Editor, defaultconfig, meta = (DisplayName = "Movie Pipeline Deadline"))
class UMoviePipelineDeadlineSettings : public UDeveloperSettings
{
	GENERATED_BODY()

public:
	UMoviePipelineDeadlineSettings();
	
	/** Gets the settings container name for the settings, either Project or Editor */
	virtual FName GetContainerName() const override { return FName("Project"); }
	/** Gets the category for the settings, some high level grouping like, Editor, Engine, Game...etc. */
	virtual FName GetCategoryName() const override { return FName("Plugins"); }
	
	/** UObject interface */
	virtual void PostEditChangeProperty(struct FPropertyChangedEvent& PropertyChangedEvent) override
	{
		Super::PostEditChangeProperty(PropertyChangedEvent);
		SaveConfig();
	}

	/** The project level Deadline preset Data Asset */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Movie Pipeline Deadline")
	TObjectPtr<UDeadlineJobPreset> DefaultJobPreset;	

	void AddPropertyToHideInMovieRenderQueue(const FName& InPropertyPath)
	{
		JobPresetPropertiesToHideInMovieRenderQueue.Add(InPropertyPath);
	}

	void RemovePropertyToHideInMovieRenderQueue(const FName& InPropertyPath)
	{
		JobPresetPropertiesToHideInMovieRenderQueue.Remove(InPropertyPath);
	}

	bool GetIsPropertyHiddenInMovieRenderQueue(const FName& InPropertyPath) const
	{
		return JobPresetPropertiesToHideInMovieRenderQueue.Contains(InPropertyPath);
	}

protected:

	UPROPERTY(config)
	TArray<FName> JobPresetPropertiesToHideInMovieRenderQueue;
};
