// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "IDetailCustomization.h"

/**
 * This customization lives in the MoviePipelineDeadline module because in order to get
 * the preset assigned to the owning job, we need to cast the owning object to the
 * UMoviePipelineDeadlineExecutorJob class. We need the assigned preset for the custom
 * ResetToDefault behaviour.
 */
class FMoviePipelineDeadlineExecutorJobCustomization : public IDetailCustomization
{
public:

	static TSharedRef< IDetailCustomization > MakeInstance();

	/** Begin IDetailCustomization interface */
	virtual void CustomizeDetails(IDetailLayoutBuilder& DetailBuilder) override;
	/** End IDetailCustomization interface */
};
